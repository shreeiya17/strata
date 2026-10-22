# Import every model module here so Base.metadata always knows about all
# tables. Alembic's env.py imports from this package, so a model that isn't
# imported here is invisible to `alembic revision --autogenerate`.
from app.models import document, tenant  # noqa: F401