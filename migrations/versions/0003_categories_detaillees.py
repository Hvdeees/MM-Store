"""Catégories détaillées (pochettes, câbles, chargeurs, cartes mémoire…) avec un ordre d'affichage

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-17

A data migration as well as a schema migration:
1. adds Category.position (display order at the till);
2. renames "Accessoires" to "Autres accessoires" and creates the detailed categories;
3. moves each existing accessory into the right new category from keywords in its name
   ("Coque silicone…" -> Pochettes et coques, "Câble USB-C…" -> Câbles). Anything unrecognised stays
   in "Autres accessoires", so no product is ever lost or left without a category.
"""
import unicodedata

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

CATEGORIES = [
    "Téléphones", "Tablettes", "Ordinateurs", "Montres connectées",
    "Pochettes et coques", "Protections d'écran", "Chargeurs", "Câbles", "Adaptateurs",
    "Batteries externes", "Écouteurs et casques", "Enceintes", "Cartes mémoire",
    "Clés USB et disques", "Souris et claviers", "Supports", "Autres accessoires",
]

# Checked in this order: "câble chargeur" is a cable, so câbles come before chargeurs.
KEYWORDS = [
    ("Pochettes et coques", ["coque", "pochette", "etui", "housse"]),
    ("Protections d'écran", ["verre trempe", "protection ecran", "protection d'ecran", "film"]),
    ("Batteries externes", ["batterie externe", "powerbank", "power bank"]),
    ("Câbles", ["cable", "cordon"]),
    ("Chargeurs", ["chargeur", "charge rapide"]),
    ("Adaptateurs", ["adaptateur", "hub", "otg", "convertisseur"]),
    ("Écouteurs et casques", ["ecouteur", "casque", "airpods", "earbuds", "kit main"]),
    ("Enceintes", ["enceinte", "haut-parleur", "speaker"]),
    ("Cartes mémoire", ["carte memoire", "micro sd", "microsd", "carte sd"]),
    ("Clés USB et disques", ["cle usb", "disque", "ssd"]),
    ("Souris et claviers", ["souris", "clavier"]),
    ("Supports", ["support", "trepied", "perche"]),
    ("Montres connectées", ["montre", "watch", "bracelet connecte"]),
    ("Tablettes", ["tablette", "ipad"]),
]


def plain(text: str) -> str:
    """'Câble Écran' -> 'cable ecran' (lowercase, no accents) for keyword matching."""
    return unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode().lower()


def category_for(product_name: str) -> str:
    name = plain(product_name)
    for category, words in KEYWORDS:
        if any(word in name for word in words):
            return category
    return "Autres accessoires"


categories = sa.table("categories", sa.column("id", sa.Integer), sa.column("name", sa.String), sa.column("position", sa.Integer))
products = sa.table("products", sa.column("id", sa.Integer), sa.column("name", sa.String), sa.column("category_id", sa.Integer))


def upgrade() -> None:
    with op.batch_alter_table("categories") as batch_op:
        batch_op.add_column(sa.Column("position", sa.Integer(), nullable=False, server_default="0"))

    conn = op.get_bind()
    conn.execute(categories.update().where(categories.c.name == "Accessoires").values(name="Autres accessoires"))
    existing = {name: id_ for id_, name in conn.execute(sa.select(categories.c.id, categories.c.name))}
    for position, name in enumerate(CATEGORIES, 1):
        if name in existing:
            conn.execute(categories.update().where(categories.c.id == existing[name]).values(position=position))
        else:
            conn.execute(categories.insert().values(name=name, position=position))
    # Categories the store created itself keep their place, after the standard ones.
    conn.execute(categories.update().where(categories.c.name.not_in(CATEGORIES)).values(position=len(CATEGORIES) + 1))

    ids = {name: id_ for id_, name in conn.execute(sa.select(categories.c.id, categories.c.name))}
    old_accessories = ids["Autres accessoires"]
    for product_id, name in conn.execute(sa.select(products.c.id, products.c.name).where(products.c.category_id == old_accessories)).all():
        conn.execute(products.update().where(products.c.id == product_id).values(category_id=ids[category_for(name)]))

    with op.batch_alter_table("categories") as batch_op:
        batch_op.alter_column("position", server_default=None)


def downgrade() -> None:
    conn = op.get_bind()
    ids = {name: id_ for id_, name in conn.execute(sa.select(categories.c.id, categories.c.name))}
    keep = {"Téléphones", "Ordinateurs", "Autres accessoires"}
    removed = [ids[n] for n in CATEGORIES if n in ids and n not in keep]
    conn.execute(products.update().where(products.c.category_id.in_(removed)).values(category_id=ids["Autres accessoires"]))
    conn.execute(categories.delete().where(categories.c.id.in_(removed)))
    conn.execute(categories.update().where(categories.c.name == "Autres accessoires").values(name="Accessoires"))
    with op.batch_alter_table("categories") as batch_op:
        batch_op.drop_column("position")
