"""Fixed lists of allowed values. Stored as plain strings in the database (simpler migrations than
database enums), and enforced by Pydantic `Literal` types at the API boundary.

Values are in French because they're shown to store staff."""
from typing import Literal

Role = Literal["admin", "vendeur"]                       # admin = store manager, vendeur = seller/cashier
PaymentMethod = Literal["especes", "carte", "virement", "cheque"]
# A sale to a reseller goes on their account ("credit"); money they hand over is recorded as a payment.
SalePaymentMethod = Literal["especes", "carte", "virement", "cheque", "credit"]
SaleStatus = Literal["validee", "annulee"]
SerialStatus = Literal["en_stock", "vendu"]
MovementReason = Literal["achat", "vente", "annulation", "ajustement"]

# Shown in this order at the till (Category.position). The manager can add or rename them later.
DEFAULT_CATEGORIES = [
    "Téléphones", "Tablettes", "Ordinateurs", "Montres connectées",
    "Pochettes et coques", "Protections d'écran", "Chargeurs", "Câbles", "Adaptateurs",
    "Batteries externes", "Écouteurs et casques", "Enceintes", "Cartes mémoire",
    "Clés USB et disques", "Souris et claviers", "Supports", "Autres accessoires",
]
