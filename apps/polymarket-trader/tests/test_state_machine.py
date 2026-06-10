"""Order state machine — every legal and illegal transition, fill math, reconcile."""
import pytest

from pmtrader.core.models import Intent, OrderStatus, Side
from pmtrader.execution.state_machine import (
    InvalidTransition,
    OrderRecord,
    TERMINAL,
)


def mk_order(size=100.0, status=OrderStatus.CREATED):
    intent = Intent(strategy="s1", token_id="t1", side=Side.BUY, price=0.40,
                    size=size, expected_edge=0.01, reasoning="test")
    rec = OrderRecord(order_id="o1", intent=intent, ts=1.0)
    # walk to requested status through legal path
    path = {
        OrderStatus.CREATED: [],
        OrderStatus.SUBMITTED: [OrderStatus.SUBMITTED],
        OrderStatus.OPEN: [OrderStatus.SUBMITTED, OrderStatus.OPEN],
        OrderStatus.REJECTED: [OrderStatus.SUBMITTED, OrderStatus.REJECTED],
    }[status]
    for st in path:
        rec.transition(st, ts=1.0, why="setup")
    return rec


class TestLegalTransitions:
    def test_full_lifecycle_to_filled(self):
        rec = mk_order()
        rec.transition(OrderStatus.SUBMITTED, 2.0, "sent")
        rec.transition(OrderStatus.OPEN, 3.0, "ack")
        rec.apply_fill(60.0, 0.40, 4.0)
        assert rec.status == OrderStatus.PARTIALLY_FILLED
        rec.apply_fill(40.0, 0.42, 5.0)
        assert rec.status == OrderStatus.FILLED

    def test_open_to_cancelled(self):
        rec = mk_order(status=OrderStatus.OPEN)
        rec.transition(OrderStatus.CANCELLED, 4.0, "user cancel")
        assert rec.status == OrderStatus.CANCELLED

    def test_submitted_to_rejected(self):
        rec = mk_order(status=OrderStatus.SUBMITTED)
        rec.transition(OrderStatus.REJECTED, 3.0, "api error")
        assert rec.status == OrderStatus.REJECTED

    def test_open_to_expired(self):
        rec = mk_order(status=OrderStatus.OPEN)
        rec.transition(OrderStatus.EXPIRED, 9.0, "gtd elapsed")
        assert rec.status == OrderStatus.EXPIRED

    def test_partial_then_cancel_remainder(self):
        rec = mk_order(status=OrderStatus.OPEN)
        rec.apply_fill(30.0, 0.40, 4.0)
        rec.transition(OrderStatus.CANCELLED, 5.0, "cancel remainder")
        assert rec.status == OrderStatus.CANCELLED
        assert rec.filled_size == 30.0

    def test_submitted_direct_fill(self):
        # fast fill can arrive before OPEN ack
        rec = mk_order(status=OrderStatus.SUBMITTED)
        rec.apply_fill(100.0, 0.40, 3.0)
        assert rec.status == OrderStatus.FILLED


class TestIllegalTransitions:
    @pytest.mark.parametrize("terminal", sorted(TERMINAL, key=str))
    def test_terminal_states_frozen(self, terminal):
        # REJECTED is only reachable from SUBMITTED; others from OPEN
        start = (OrderStatus.SUBMITTED if terminal == OrderStatus.REJECTED
                 else OrderStatus.OPEN)
        rec = mk_order(status=start)
        if terminal == OrderStatus.FILLED:
            rec.apply_fill(100.0, 0.40, 4.0)
        else:
            rec.transition(terminal, 4.0, "end")
        for target in [OrderStatus.OPEN, OrderStatus.SUBMITTED, OrderStatus.CANCELLED]:
            with pytest.raises(InvalidTransition):
                rec.transition(target, 5.0, "no")

    def test_created_cannot_jump_to_open(self):
        rec = mk_order()
        with pytest.raises(InvalidTransition):
            rec.transition(OrderStatus.OPEN, 2.0, "skip submit")

    def test_cannot_fill_cancelled_order(self):
        rec = mk_order(status=OrderStatus.OPEN)
        rec.transition(OrderStatus.CANCELLED, 4.0, "cancel")
        with pytest.raises(InvalidTransition):
            rec.apply_fill(10.0, 0.40, 5.0)


class TestFillMath:
    def test_avg_price_accumulates(self):
        rec = mk_order(status=OrderStatus.OPEN)
        rec.apply_fill(60.0, 0.40, 4.0)
        rec.apply_fill(40.0, 0.42, 5.0)
        assert rec.avg_fill_price == pytest.approx(0.408)
        assert rec.filled_size == 100.0

    def test_overfill_raises(self):
        rec = mk_order(status=OrderStatus.OPEN)
        with pytest.raises(ValueError):
            rec.apply_fill(101.0, 0.40, 4.0)

    def test_zero_fill_raises(self):
        rec = mk_order(status=OrderStatus.OPEN)
        with pytest.raises(ValueError):
            rec.apply_fill(0.0, 0.40, 4.0)


class TestReconcile:
    def test_api_says_filled_local_open_emits_synthetic_fill(self):
        rec = mk_order(status=OrderStatus.OPEN)
        rec.apply_fill(30.0, 0.40, 4.0)
        gap = rec.reconcile(api_status="FILLED", api_filled_size=100.0,
                            api_avg_price=0.41, ts=6.0)
        assert rec.status == OrderStatus.FILLED
        assert rec.filled_size == 100.0
        assert gap == pytest.approx(70.0)

    def test_reconcile_fill_gap_with_no_prior_fills(self):
        rec = mk_order(status=OrderStatus.OPEN)
        gap = rec.reconcile(api_status="FILLED", api_filled_size=100.0,
                            api_avg_price=0.41, ts=6.0)
        assert gap == pytest.approx(100.0)
        assert rec.status == OrderStatus.FILLED
        assert rec.avg_fill_price == pytest.approx(0.41)

    def test_api_says_cancelled_local_open(self):
        rec = mk_order(status=OrderStatus.OPEN)
        gap = rec.reconcile(api_status="CANCELLED", api_filled_size=0.0,
                            api_avg_price=0.0, ts=6.0)
        assert rec.status == OrderStatus.CANCELLED
        assert gap == 0.0

    def test_reconcile_agreement_is_noop(self):
        rec = mk_order(status=OrderStatus.OPEN)
        gap = rec.reconcile(api_status="OPEN", api_filled_size=0.0,
                            api_avg_price=0.0, ts=6.0)
        assert rec.status == OrderStatus.OPEN
        assert gap == 0.0

    def test_unknown_api_status_marks_expired_orphan(self):
        rec = mk_order(status=OrderStatus.OPEN)
        rec.reconcile(api_status="UNKNOWN", api_filled_size=0.0,
                      api_avg_price=0.0, ts=6.0)
        assert rec.status == OrderStatus.EXPIRED
        assert rec.orphaned is True


class TestAudit:
    def test_every_transition_audited(self):
        rec = mk_order()
        rec.transition(OrderStatus.SUBMITTED, 2.0, "sent")
        rec.transition(OrderStatus.OPEN, 3.0, "ack")
        rec.apply_fill(100.0, 0.40, 4.0)
        states = [a[2] for a in rec.audit]
        assert states == [OrderStatus.SUBMITTED, OrderStatus.OPEN, OrderStatus.FILLED]
        assert all(len(a) == 4 for a in rec.audit)  # (ts, from, to, why)
