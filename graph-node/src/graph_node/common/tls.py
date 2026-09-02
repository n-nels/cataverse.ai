"""Make Python verify TLS against the operating system's trust store.

Python ships its own bundle of certificate authorities and ignores the one the
operating system maintains. On an ordinary machine the two agree. On a managed
network they do not: many institutions run a security appliance that terminates
TLS, inspects the traffic, and re-signs it with a private certificate
authority. Windows is told to trust that authority, so browsers work. Python
has never heard of it, so it sees a self-signed certificate in the chain and
refuses the connection.

That is exactly what the lab machine hit connecting to Aura on 2026-09-02:

    SSLCertVerificationError: certificate verify failed:
    self-signed certificate in certificate chain

`truststore` redirects Python's verification to the OS store, so the private
authority is trusted precisely because the machine's administrator trusts it.

This is deliberately *not* the same as disabling verification. The alternative
- `neo4j+ssc://`, which accepts any certificate - would also accept one from
something that is not the security appliance, which is the whole point of
verifying. Here every certificate is still checked; the set of authorities is
simply the machine's own.

Harmless on an unmanaged machine: the OS store holds the same public
authorities Python would have used. `pip` itself does this by default.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def use_system_trust_store() -> bool:
    """Verify TLS against the OS trust store. True if it took effect.

    Never raises. If `truststore` is unavailable or the platform does not
    support it, Python's bundled authorities are used as before - which is
    correct everywhere except behind TLS interception.
    """
    try:
        import truststore
    except ImportError:
        logger.debug("truststore not installed; using Python's bundled CAs")
        return False

    try:
        truststore.inject_into_ssl()
    except Exception as exc:  # pragma: no cover - platform dependent
        logger.debug("could not use the system trust store: %s", exc)
        return False

    logger.debug("verifying TLS against the system trust store")
    return True
