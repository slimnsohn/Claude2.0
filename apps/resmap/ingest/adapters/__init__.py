class MissingCredentialsError(Exception):
    """Raised by an adapter when its venue credentials are absent.
    The ingest loop catches this and skips the venue instead of crashing,
    so keyless venues (Polymarket) keep working while creds are pending."""
