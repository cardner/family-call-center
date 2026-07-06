"""Shared Flask extension instances.

Kept in their own module so blueprints can import them (e.g. to decorate routes
with rate limits) without importing the application factory and causing circular
imports.
"""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf import CSRFProtect

csrf = CSRFProtect()

limiter = Limiter(key_func=get_remote_address)
