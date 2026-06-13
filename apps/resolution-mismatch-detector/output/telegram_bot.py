"""Telegram bot with inline actions for mismatch alerts."""

import json
import logging
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from db.database import Database
from analysis.claude_client import ClaudeClient
from analysis.rules_adjusted import estimate_rules_adjusted_probability

logger = logging.getLogger(__name__)


async def send_mismatch_alert(bot, chat_id: str, analysis: dict, market: dict, db: Database):
    """Send a mismatch alert with inline action buttons."""
    severity_emoji = {"high": "\U0001f534", "medium": "\U0001f7e1", "low": "\U0001f7e2"}
    emoji = severity_emoji.get(analysis.get("severity", ""), "\u26aa")

    position_note = ""
    pos = db.get_position(market["id"])
    if pos:
        position_note = (
            f"\n\u26a0\ufe0f YOU HOLD: {pos['side']} @ {pos['avg_price']:.2f} "
            f"x {pos['quantity']}"
        )

    price_str = f"{market['current_yes_price']:.0%}" if market.get("current_yes_price") else "N/A"
    volume_str = f"${market.get('volume', 0):,.0f}"

    text = (
        f"{emoji} *{analysis['severity'].upper()} MISMATCH*\n\n"
        f"*{market['platform'].upper()}:* {market['title']}\n"
        f"Price: {price_str}\n"
        f"Volume: {volume_str}\n"
        f"Priority: {analysis.get('priority_score', 0):.2f}\n\n"
        f"*Retail assumes:* {analysis.get('retail_assumption', 'N/A')}\n"
        f"*Rules say:* {analysis.get('actual_resolution', 'N/A')}\n"
        f"*Gap:* {analysis.get('mismatch_categories', 'N/A')}"
        f"{position_note}"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("\U0001f50d Analyze Deeper", callback_data=f"deeper:{market['id']}"),
            InlineKeyboardButton("\U0001f441 Track", callback_data=f"track:{market['id']}"),
        ],
        [
            InlineKeyboardButton("\u274c Dismiss", callback_data=f"dismiss:{market['id']}"),
        ],
    ])

    await bot.send_message(
        chat_id=chat_id, text=text,
        reply_markup=keyboard, parse_mode="Markdown",
    )


async def send_arb_alert(bot, chat_id: str, match: dict, arb_signal: dict):
    """Send a cross-platform arbitrage alert."""
    divergence_lines = "\n".join(
        f"  \u2022 {d}" for d in arb_signal.get("rule_divergence", [])
    )
    text = (
        f"\U0001f500 *CROSS-PLATFORM ARB DETECTED*\n\n"
        f"*Event:* Same event, different rules\n"
        f"*Polymarket:* {match.get('poly_title', match['polymarket_id'])} "
        f"@ {arb_signal['poly_price']:.0%}\n"
        f"*Kalshi:* {match.get('kalshi_title', match['kalshi_id'])} "
        f"@ {arb_signal['kalshi_price']:.0%}\n\n"
        f"*Rule Differences:*\n{divergence_lines}\n\n"
        f"*Suggested:* {arb_signal.get('suggested_action', 'Review manually')}"
    )
    await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")


async def send_rule_change_alert(bot, chat_id: str, market: dict, position: dict, impact: dict):
    """Send alert when rules change on a held position."""
    text = (
        f"\u26a0\ufe0f *RULE CHANGE ON HELD POSITION*\n\n"
        f"*{market['platform'].upper()}:* {market['title']}\n"
        f"*Your position:* {position['side']} @ {position['avg_price']:.2f} "
        f"x {position['quantity']}\n\n"
        f"\U0001f4dd *Rule Change Analysis:*\n{impact.get('summary', 'N/A')}\n\n"
        f"*Impact on your position:* {impact.get('position_impact', 'N/A')}\n"
        f"*Suggested action:* {impact.get('suggested_action', 'N/A')}\n"
        f"*Urgency:* {impact.get('urgency', 'unknown')}"
    )
    await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button callbacks."""
    query = update.callback_query
    action, market_id = query.data.split(":", 1)

    db = context.bot_data.get("db")
    if not db:
        db = Database()
        context.bot_data["db"] = db

    if action == "deeper":
        market = db.get_market(market_id)
        analysis = db.get_latest_analysis(market_id)
        if not market or not analysis:
            await query.answer("Market not found")
            return

        client = context.bot_data.get("claude_client")
        if not client:
            client = ClaudeClient()
            context.bot_data["claude_client"] = client

        deeper = estimate_rules_adjusted_probability(client, market, analysis)
        await query.answer()

        prob = deeper.get("rules_adjusted_probability", "N/A")
        mkt = deeper.get("market_price", "N/A")
        div = deeper.get("divergence", "N/A")
        conf = deeper.get("confidence_in_estimate", "N/A")

        await query.message.reply_text(
            f"\U0001f4ca *Rules-Adjusted Probability:* {prob}\n"
            f"\U0001f4c8 *Market Price:* {mkt}\n"
            f"\U0001f4d0 *Divergence:* {div}\n"
            f"\U0001f3af *Confidence:* {conf}\n\n"
            f"{deeper.get('reasoning', '')}",
            parse_mode="Markdown",
        )

    elif action == "dismiss":
        db.dismiss_alert(market_id, dismissed_at=datetime.utcnow().isoformat())
        await query.answer("Dismissed \u2014 won't alert again")
        await query.message.edit_reply_markup(reply_markup=None)

    elif action == "track":
        db.add_to_watchlist(market_id, added_at=datetime.utcnow().isoformat())
        await query.answer("Added to watchlist")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command — show summary stats."""
    db = context.bot_data.get("db")
    if not db:
        db = Database()
        context.bot_data["db"] = db

    high = db.get_analyses(severity="high")
    medium = db.get_analyses(severity="medium")
    positions = db.get_all_positions()
    watchlist = db.get_watchlist()

    text = (
        f"\U0001f4cb *Status*\n\n"
        f"High severity: {len(high)}\n"
        f"Medium severity: {len(medium)}\n"
        f"Active positions: {len(positions)}\n"
        f"Watchlist: {len(watchlist)}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


def create_bot_application() -> Application:
    """Create and configure the Telegram bot application."""
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(CommandHandler("status", cmd_status))
    return app
