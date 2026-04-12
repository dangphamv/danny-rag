from slowapi import Limiter
from slowapi.util import get_remote_address

# Single project-wide rate limiter. Shared between main.py (app.state) and
# any route module that needs @limiter.limit(...) decorators.
limiter = Limiter(key_func=get_remote_address)
