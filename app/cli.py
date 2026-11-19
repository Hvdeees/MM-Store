"""Command-line tools.

    python -m app.cli create-admin --email gerant@boutique.ma --name "Nom du gérant"
    python -m app.cli seed-demo        # sample products + a demo seller, to try the app

The first admin can't be created through the API (every API route needs a logged-in admin to create
users), so it's done from the server's terminal.
"""
import argparse
import getpass
import sys

from sqlalchemy import func, select

from app.config import settings
from app.database import SessionLocal
from app.models import Category, Product, Reseller, SerialUnit, StockMovement, User
from app.security import hash_password


def create_admin(email: str, name: str, password: str | None) -> None:
    password = password or getpass.getpass("Mot de passe (8 caractères minimum) : ")
    if not 8 <= len(password) <= 72:
        sys.exit("Le mot de passe doit contenir entre 8 et 72 caractères.")
    with SessionLocal() as db:
        if db.scalar(select(User).where(func.lower(User.email) == email.lower())):
            sys.exit(f"Un compte existe déjà pour {email}.")
        db.add(User(email=email.lower(), full_name=name, role="admin", password_hash=hash_password(password)))
        db.commit()
    print(f"Administrateur créé : {email}")


DEMO_PRODUCTS = [
    # (sku, name, brand, category, price DH, cost DH, IMEIs or quantity)
    ("TEL-A55-128", "Samsung Galaxy A55 128 Go", "Samsung", "Téléphones", 3999, 3400,
     ["356789012345671", "356789012345672", "356789012345673"]),
    ("TEL-IP15-128", "iPhone 15 128 Go", "Apple", "Téléphones", 9490, 8600, ["353456789012341", "353456789012342"]),
    ("TEL-RN13", "Redmi Note 13 256 Go", "Xiaomi", "Téléphones", 2499, 2050, ["868123456789011"]),
    ("TAB-TABA9", "Galaxy Tab A9 64 Go", "Samsung", "Tablettes", 1990, 1650, ["R9XT40A1B2C"]),
    ("PC-HP15-I5", "HP 15 Core i5 16 Go / 512 Go", "HP", "Ordinateurs", 7290, 6300, ["5CD1234ABC", "5CD1234ABD"]),
    ("PC-MBA-M3", "MacBook Air M3 13\"", "Apple", "Ordinateurs", 13990, 12500, ["C02XG1JZJGH5"]),
    ("POC-A55-SIL", "Coque silicone Galaxy A55", "Generic", "Pochettes et coques", 99, 35, 25),
    ("POC-IP15-CLR", "Coque transparente iPhone 15", "Generic", "Pochettes et coques", 79, 25, 18),
    ("PRO-VTR-IP15", "Verre trempé iPhone 15", "Generic", "Protections d'écran", 69, 15, 40),
    ("CHG-USBC-20", "Chargeur USB-C 20W", "Anker", "Chargeurs", 199, 110, 15),
    ("CHG-VOIT-2P", "Chargeur voiture 2 ports", "Baseus", "Chargeurs", 149, 80, 8),
    ("CAB-USBC-1M", "Câble USB-C 1 m", "Anker", "Câbles", 79, 30, 2),
    ("CAB-LGT-1M", "Câble Lightning 1 m", "Generic", "Câbles", 69, 22, 20),
    ("ADP-C-JACK", "Adaptateur USB-C vers jack 3,5 mm", "Generic", "Adaptateurs", 59, 18, 12),
    ("BAT-10K", "Batterie externe 10 000 mAh", "Xiaomi", "Batteries externes", 249, 160, 7),
    ("ECO-JBL-520", "Écouteurs JBL Tune 520BT", "JBL", "Écouteurs et casques", 549, 420, 6),
    ("SD-SAN-64", "Carte mémoire microSD 64 Go", "SanDisk", "Cartes mémoire", 99, 55, 30),
    ("SUP-VOIT-MAG", "Support voiture magnétique", "Generic", "Supports", 89, 35, 10),
]


def seed_demo() -> None:
    if settings.environment == "production":
        sys.exit("Données de démonstration interdites en production.")
    with SessionLocal() as db:
        if db.scalar(select(func.count(Product.id))):
            sys.exit("La base contient déjà des produits : données de démonstration non ajoutées.")
        admin = db.scalar(select(User).where(User.role == "admin"))
        if admin is None:
            sys.exit("Créez d'abord un administrateur : python -m app.cli create-admin ...")
        categories = {c.name: c.id for c in db.scalars(select(Category))}
        for sku, name, brand, category, price, cost, stock in DEMO_PRODUCTS:
            serial_tracked = isinstance(stock, list)
            product = Product(sku=sku, name=name, brand=brand, category_id=categories[category],
                              price_centimes=price * 100, cost_centimes=cost * 100,
                              # demo reseller price: halfway between cost and normal price, rounded to the dirham
                              wholesale_price_centimes=round((price + cost) / 2) * 100,
                              quantity=len(stock) if serial_tracked else stock, tracks_serial=serial_tracked)
            db.add(product)
            db.flush()
            if serial_tracked:
                db.add_all(SerialUnit(product_id=product.id, serial=s) for s in stock)
            db.add(StockMovement(product_id=product.id, change=product.quantity, reason="achat",
                                 user_id=admin.id, note="Stock de démonstration"))
        db.add_all([Reseller(name="Phone House Agadir", city="Agadir", contact_name="Hamid", phone="0661 23 45 67",
                             notes="Paie en fin de mois"),
                    Reseller(name="Tech Corner Casablanca", city="Casablanca", contact_name="Salma", phone="0662 98 76 54")])
        if not db.scalar(select(User).where(User.email == "vendeur@demo.ma")):
            db.add(User(email="vendeur@demo.ma", full_name="Vendeur Démo", role="vendeur",
                        password_hash=hash_password("vendeur123")))
        db.commit()
    print("Données de démonstration ajoutées. Compte vendeur : vendeur@demo.ma / vendeur123")


def main() -> None:
    parser = argparse.ArgumentParser(description="Outils d'administration de la boutique")
    sub = parser.add_subparsers(dest="command", required=True)
    admin = sub.add_parser("create-admin", help="Créer un compte administrateur")
    admin.add_argument("--email", required=True)
    admin.add_argument("--name", required=True)
    admin.add_argument("--password", help="(sinon demandé de façon masquée)")
    sub.add_parser("seed-demo", help="Ajouter des produits de démonstration")
    args = parser.parse_args()

    if args.command == "create-admin":
        create_admin(args.email, args.name, args.password)
    else:
        seed_demo()


if __name__ == "__main__":
    main()
