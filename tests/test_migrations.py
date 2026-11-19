"""Guards against the classic mistake: changing models.py but forgetting to write a migration.

Applies every migration to an empty database, then asks Alembic to compare the result with models.py.
Any difference = a missing migration, and this test fails.
"""
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text

from app.constants import DEFAULT_CATEGORIES
from app.models import Base
from tests.conftest import TEST_DATABASE_URL


def test_migrations_match_models(tmp_path):
    engine = create_engine(TEST_DATABASE_URL or f"sqlite:///{tmp_path / 'migrations.db'}")
    with engine.begin() as connection:
        Base.metadata.drop_all(connection)
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))

    config = Config("alembic.ini")
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")

    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        assert compare_metadata(context, Base.metadata) == []
        names = connection.execute(text("SELECT name FROM categories ORDER BY position")).scalars().all()
        assert names == DEFAULT_CATEGORIES

    with engine.begin() as connection:   # downgrade must work too, and leave nothing behind
        config.attributes["connection"] = connection
        command.downgrade(config, "base")
    engine.dispose()


def test_existing_accessories_are_sorted_into_new_categories(tmp_path):
    """A store that already has products in "Accessoires" gets them moved to the right new category."""
    engine = create_engine(TEST_DATABASE_URL or f"sqlite:///{tmp_path / 'regroup.db'}")
    with engine.begin() as connection:
        Base.metadata.drop_all(connection)
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    config = Config("alembic.ini")
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0002")
        acc = connection.execute(text("SELECT id FROM categories WHERE name = 'Accessoires'")).scalar_one()
        tel = connection.execute(text("SELECT id FROM categories WHERE name = 'Téléphones'")).scalar_one()
        for i, (name, category) in enumerate([("Coque Galaxy A15", acc), ("Câble chargeur USB-C", acc),
                                              ("Chargeur 25W", acc), ("Carte Micro SD 128 Go", acc),
                                              ("Porte-clés MM", acc), ("Galaxy A15", tel)]):
            connection.execute(text("INSERT INTO products (sku, name, category_id, price_centimes, cost_centimes, quantity, "
                                    "low_stock_threshold, tracks_serial, is_active, created_at) VALUES "
                                    "(:sku, :name, :cat, 100, 50, 0, 3, false, true, CURRENT_TIMESTAMP)"),
                               {"sku": f"S{i}", "name": name, "cat": category})
        command.upgrade(config, "head")
        rows = dict(connection.execute(text(
            "SELECT p.name, c.name FROM products p JOIN categories c ON c.id = p.category_id")).all())
        command.downgrade(config, "base")
    engine.dispose()
    assert rows == {
        "Coque Galaxy A15": "Pochettes et coques",
        "Câble chargeur USB-C": "Câbles",          # a cable, even though "chargeur" is in the name
        "Chargeur 25W": "Chargeurs",
        "Carte Micro SD 128 Go": "Cartes mémoire",
        "Porte-clés MM": "Autres accessoires",       # not recognised: stays, never lost
        "Galaxy A15": "Téléphones",                  # only accessories are moved
    }
