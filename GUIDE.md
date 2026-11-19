# The complete guide to MM Store

This guide explains how the whole system works, why each decision was made, and how to rebuild it yourself.
Read it with the code open next to it.

**Contents**
1. The big picture
2. Life of one request: a sale, from click to database and back
3. Reading order: every file, in the order to read it
4. The concepts, one by one
5. Running it
6. Putting it in a real store
7. Rebuild it yourself: a step-by-step plan
8. Interview questions you will get about this project
9. Known limitations

---

## 1. The big picture

```
 Browser (French web interface: app/static/)
    │   HTTP + JSON, header "Authorization: Bearer <JWT>"
    ▼
 FastAPI (app/main.py + app/routers/*.py)
    │   validates input (schemas.py), checks login and role (security.py)
    ▼
 SQLAlchemy (app/models.py, app/database.py)
    │   turns Python objects and statements into SQL
    ▼
 PostgreSQL (the data: users, products, IMEIs, sales, stock movements)
```

There are three layers, and each one has one job:

- **The interface** (HTML/CSS/JS) only displays data and sends requests. It contains no business rules. Even if someone bypasses it and calls the API directly, every rule still holds.
- **The API** enforces the rules: who may do what, what counts as valid input, and how a sale changes stock.
- **The database** stores the data and is the last line of defence: `UNIQUE` on SKUs and IMEIs, and `CHECK (quantity >= 0)`.

**Rule of thumb:** never trust the client. The JavaScript limits the cart quantity to the stock available, but the server checks it again anyway, because anyone can send any request with `curl`.

### The data model

```
 users ──< sales ──< sale_items >── products >── categories
   │                     │              │
   │                     └──< serial_units (one row per phone/computer, by IMEI)
   └──< stock_movements >───────────────┘
```

- **Product**: a catalogue entry ("Samsung Galaxy A55 128 Go"), with its price, cost, quantity and low-stock threshold.
- **SerialUnit**: one physical phone or computer, identified by its IMEI or serial number, with status `en_stock` or `vendu`. Only products with `tracks_serial = true` have these.
- **Sale** / **SaleItem**: a receipt and its lines. Each line copies the price and cost at the moment of sale, plus the IMEIs sold.
- **StockMovement**: the audit trail. Every change to `Product.quantity` writes one row: +10 `achat` (delivery), −1 `vente` (sale), +1 `annulation` (cancellation), −1 `ajustement` (manual correction).

---

## 2. Life of one request: a sale

A seller sells one Samsung A55 (IMEI 356789012345671) and 2 phone cases, paid by card. Here is exactly what happens.

**1. Browser (`app.js`, `checkout()`)** builds this JSON and sends `POST /api/sales`:
```json
{"items": [{"product_id": 1, "quantity": 1, "serials": ["356789012345671"]},
           {"product_id": 6, "quantity": 2, "serials": []}],
 "payment_method": "carte", "discount_centimes": 0}
```
The `api()` helper adds the header `Authorization: Bearer eyJhbGciOi...`.

**2. FastAPI routing (`main.py`)** matches the path to `create_sale` in `routers/sales.py`.

**3. Dependencies run before the function body.** The signature is
`create_sale(body: SaleCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db))`, so FastAPI:
- calls `get_db()`, which opens a database session;
- calls `get_current_user()`, which decodes the JWT, checks its signature and expiry, and loads the user. If anything is wrong, it stops here with a 401;
- validates the JSON against `SaleCreate`. A negative quantity or an unknown payment method stops here with a 422, and the French error handler in `main.py` turns it into "Données invalides : …".

**4. `create_sale` runs, inside one transaction:**
1. It merges repeated lines for the same product.
2. It inserts the `Sale` row and calls `flush()`, which sends the INSERT without committing, so `sale.id` exists.
3. For each product:
   - If it's a phone, it runs `UPDATE serial_units SET status='vendu' WHERE serial IN (...) AND product_id=1 AND status='en_stock'`. If `rowcount` isn't exactly 1, that IMEI is unknown, already sold, or belongs to another product, so it raises a 409.
   - It runs `UPDATE products SET quantity = quantity - 1 WHERE id = 1 AND quantity >= 1`. If `rowcount` is 0, there isn't enough stock, so it raises a 409.
   - It adds a `SaleItem` with the price copied, and a `StockMovement` of −1.
4. It checks that the discount isn't larger than the subtotal, then computes the total.
5. It calls `commit()`. Everything becomes permanent at once.

If anything raises an error at any point, `rollback()` undoes every step: the stock, the IMEI status, the movements and the sale row.

**5. Response:** `to_out()` converts the database objects into a `SaleOut`, and FastAPI sends back JSON with status 201.

**6. Browser:** shows the receipt in the pop-up and empties the cart.

Once you understand this one request, you understand 80% of the backend.

---

## 3. Reading order

Read the files in this order. Each one builds on the ones before it.

| # | File | What to understand |
| --- | --- | --- |
| 1 | `app/config.py` | Settings come from environment variables; the app refuses to start in production without `SECRET_KEY` |
| 2 | `app/database.py` | The engine (connection pool); `get_db` gives one session per request and always closes it |
| 3 | `app/constants.py` | Allowed values (roles, payment methods…) as `Literal` types |
| 4 | `app/models.py` | Every table, the constraints, why money is in centimes, why prices are copied |
| 5 | `app/schemas.py` | The API's input and output shapes; `extra="forbid"`; no `quantity` on product creation |
| 6 | `app/security.py` | bcrypt, JWT creation and checking, `get_current_user`, `require_admin` |
| 7 | `app/routers/auth.py` | Login, `me`, password change |
| 8 | `app/routers/users.py` | Admin-only router (`dependencies=[Depends(require_admin)]`) |
| 9 | `app/routers/categories.py` | The simplest CRUD router: start your rebuild with this pattern |
| 10 | `app/stock.py` | IMEI normalisation and `record_movement` |
| 11 | `app/routers/products.py` | Search (including by IMEI), restocking with IMEIs, atomic adjustments, hiding the cost from sellers |
| 12 | `app/routers/sales.py` | **The heart of the project.** Read `create_sale` three times. |
| 13 | `app/timeutils.py` + `app/routers/reports.py` | Local day → UTC range; SQL aggregation |
| 14 | `app/main.py` | Wiring it all together, the French error handler, serving the interface |
| 15 | `migrations/` | Alembic; read `versions/0001_tables_initiales.py` next to `models.py` |
| 16 | `tests/conftest.py`, then each test file | Fixtures; the tests describe the expected behaviour precisely |
| 17 | `app/static/app.js` | `api()`, `esc()`, the views, the cart |
| 18 | `Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml` | How it runs in production and in CI |

---

## 4. The concepts

### 4.1 HTTP status codes used here
| Code | Meaning in this app | Example |
| --- | --- | --- |
| 200 | OK | Get a product |
| 201 | Created | A sale was recorded |
| 204 | Done, nothing to return | Password changed |
| 400 | Request understood but not allowed by the rules | Discount larger than the subtotal |
| 401 | Not logged in, or the token is invalid or expired | No `Authorization` header |
| 403 | Logged in but not allowed | A seller opens the reports |
| 404 | Doesn't exist (or isn't yours) | Another seller's sale |
| 409 | Conflicts with the current state | Out of stock; duplicate SKU; IMEI already sold |
| 422 | Input fails validation | Negative price; unknown field |

**Why 404 and not 403 for another seller's sale?** A 403 would confirm that sale #57 exists. A 404 reveals nothing.

### 4.2 FastAPI dependencies (`Depends`)
A dependency is a function FastAPI runs before your endpoint, passing its result in as a parameter.
`get_db` opens and closes the session. `get_current_user` builds on `oauth2_scheme`, which reads the header, and on `get_db`.
`require_admin` builds on `get_current_user`. Chaining them like this keeps every endpoint short. Protecting a whole
router takes one line: `APIRouter(..., dependencies=[Depends(require_admin)])`.

In tests, `app.dependency_overrides[get_db] = ...` swaps in the test database without touching the app code.

### 4.3 Validation with Pydantic
`schemas.py` describes what's allowed: `Field(gt=0)`, `Literal["especes", ...]`, `EmailStr`, `max_length`.
FastAPI rejects bad input before your code runs. Two deliberate choices:
- `extra="forbid"`: a typo like `"qantity"` is an error instead of being silently ignored.
- `ProductCreate` has **no** `quantity` field, so stock can only enter through `/restock`, which always writes a movement.
  The rule "every stock change has a reason" is enforced by the API's shape itself.

### 4.4 SQLAlchemy: the session, `flush` and `commit`
- A **session** is a unit of work: you add and change objects, and it turns them into SQL.
- `flush()` sends the pending SQL to the database **inside the current transaction**, so you get generated ids, but nothing is permanent yet.
- `commit()` makes everything permanent.
- `rollback()` throws away everything since the last commit.

There are two ways to change data:
- **ORM style:** `product.price_centimes = 300`, then commit. Simple, and fine when there's no race.
- **Statement style:** `db.execute(update(Product).where(...).values(...))`. Used whenever the new value depends on the current
  value in the database (stock), because the check and the change happen in **one** SQL statement.

### 4.5 Transactions: all-or-nothing
A sale touches several tables. If the 3rd line fails after the first two lines already reduced stock, you can't be
left with half a sale. `try: ... commit() except: rollback(); raise` guarantees all-or-nothing.
`test_failed_sale_changes_nothing` proves it: after a failed 3-line sale, the stock, the IMEI status, the movements and the sales list are all unchanged.

### 4.6 Race conditions and the conditional UPDATE (the best interview story)
The naive code:
```python
product = db.get(Product, id)
if product.quantity < qty: raise ...        # (1) check
product.quantity -= qty                     # (2) write
db.commit()
```
Two requests can both pass step (1) before either reaches step (2): two people "buy" the last phone, and stock goes wrong.

The fix:
```sql
UPDATE products SET quantity = quantity - :n WHERE id = :id AND quantity >= :n
```
The database runs this atomically and locks the row while it does. The second request re-checks `quantity >= n` after the first commits, matches 0 rows, and gets a 409.

**Proof:** `tests/test_concurrency.py` releases 10 threads at the same instant to buy the last unit, on real PostgreSQL.
With this code: 1 success and 9 refusals. With the naive version, tried during development: **10 successes**, the same phone sold 10 times.
The same pattern protects IMEIs (`WHERE status='en_stock'`), cancellations (`WHERE status='validee'`, so stock is never restored twice) and adjustments (`WHERE quantity + change >= 0`).

Other approaches you should know by name: `SELECT ... FOR UPDATE` (pessimistic row locking), optimistic locking with
a version column, and the SERIALIZABLE isolation level. The conditional UPDATE is the simplest of them and it's enough here.

### 4.7 Money in centimes
`0.1 + 0.2 == 0.30000000000000004` in floating point. Over thousands of sales, those errors become wrong totals.
Integers are exact: 3 999,00 DH is stored as `399900`. The interface converts with `toCentimes()` and `money()`.
(The alternative is `Decimal` / SQL `NUMERIC`. Integers are simpler, and they're what Stripe does.)

### 4.8 Authentication: bcrypt and JWT
- **bcrypt** hashes passwords with a random salt and a deliberately slow algorithm (`rounds=12`, about 0.25 s per hash).
  A stolen database doesn't give away passwords, and guessing them is slow. Tests use `rounds=4` to stay fast.
- **JWT**: after login the server signs `{"sub": user_id, "role": ..., "exp": ...}` with `SECRET_KEY`. The browser
  sends it back on every request. Changing a single character breaks the signature, so it can't be forged.
- **Why reload the user on every request?** A JWT stays valid until it expires (12 hours here). Checking the database
  each time means a deactivated employee is locked out immediately (`test_deactivated_user_is_locked_out_immediately`).
- Login gives the same message for a wrong email and a wrong password, so attackers can't discover which emails have accounts.

### 4.9 Authorization: what each role can do
| | Admin | Vendeur |
| --- | --- | --- |
| Sell, search products, look up IMEIs | ✓ | ✓ |
| See purchase prices and margins | ✓ | ✗ (`cost_centimes` is `null`) |
| See sales | all | own only |
| Create or edit products, receive stock, adjust stock, cancel sales | ✓ | ✗ |
| Reports, user management | ✓ | ✗ |

Hiding the cost happens **on the server** (`to_out()` in `products.py`). Hiding it only in the interface would be
pointless, because the seller could just read the API response.

### 4.10 IMEI tracking
Accessories are counted (`quantity`). Phones and computers are **individuals**: a customer comes back with
*this* phone, under warranty. So every unit gets a `SerialUnit` row when it's delivered (`/restock` requires exactly
one IMEI per unit), changes to `vendu` when sold, and goes back to `en_stock` if the sale is cancelled. `SaleItem.serial_numbers`
keeps a permanent record of which IMEIs were on each receipt. `GET /api/serials/{imei}` answers the question
"did we sell this phone, when, and to whom?"

### 4.11 History you never lose
- Products are **archived** (`is_active = false`), never deleted: old sales still point to them.
- Sales are **cancelled** (`status = 'annulee'`, plus who, when and why), never deleted.
- Every stock change is a `StockMovement`. If the stock looks wrong, the history shows exactly what happened.

### 4.12 Time zones
Times are stored in UTC and converted only for display and reports. "Sales on 18 November" means midnight to midnight
**in Casablanca**. `timeutils.local_range_utc` converts that local day into a UTC time range.

Real-world proof that this matters: Morocco used UTC+1 (UTC+0 during Ramadan) until **20 September 2026**, then
switched permanently to UTC+0. Code with a hard-coded `+01:00` would now put late-evening sales on the wrong day.
`zoneinfo` applies the official rules for each date, and `test_late_evening_sale_counts_on_moroccan_day` checks both
periods. The Dockerfile sets `PYTHONTZPATH=""` so the app uses the up-to-date `tzdata` package instead of the
system's possibly outdated copy.

### 4.13 Migrations (Alembic)
In production you can't drop and recreate tables, because that would delete the store's data. A migration is a versioned
script that changes the schema step by step (`upgrade`) and can undo it (`downgrade`).
Workflow when you change `models.py`:
```bash
alembic revision --autogenerate -m "Ajout de la garantie"   # writes migrations/versions/xxxx.py
# READ the generated file: autogenerate is a draft, not gospel
alembic upgrade head
```
`tests/test_migrations.py` applies all migrations to an empty database and fails if the result differs from `models.py`,
which catches "I changed the model but forgot the migration."

### 4.14 Testing strategy
- Each test gets a **fresh database** (`session_factory` fixture), so tests never depend on each other.
- Tests call the API like a real client would (`TestClient`), so they cover routing, auth, validation and the database together.
- They run on **SQLite** by default (fast, nothing to install) and on **PostgreSQL** when `TEST_DATABASE_URL` is set. CI does both.
  The concurrency test runs only on PostgreSQL, because an in-memory SQLite database can't run transactions in parallel.
- Read the test names as a specification: `test_cannot_cancel_twice`, `test_price_is_frozen_at_time_of_sale`, and so on.

### 4.15 The web interface
Designed for shop staff, not engineers: big photo tiles you tap to sell, a cart drawn like a paper ticket, plain French words ("Encaisser", "Ajouter du stock", "Corriger le stock"), and a layout that switches to a bottom menu on phones.
The look is a premium phone store in white and gold: product photos on a cool grey stage, pill buttons and iOS-style segmented controls, deep gold (#8c6a34, readable on white) for actions, a brushed-gold gradient only for the MM monogram and the phone frame, and the till's ticket shown inside a gold phone with a Dynamic-Island-style notch (on a real phone, the frame disappears). Manrope for text and amounts, Cormorant Garamond only for the monogram. All choices are CSS variables at the top of `styles.css`; fonts are bundled so the till looks the same offline.
Plain JavaScript, no framework, no build step: FastAPI serves `app/static/` directly.
- `api()` is the single place that talks to the server: it adds the token, handles 401s by logging out, and turns errors into messages.
- Each tab is a function in `views` that fetches data and renders HTML.
- **XSS protection:** every server value goes through `esc()` before it's inserted into HTML. Without it, a product
  named `<img src=x onerror=...>` would run code in the manager's browser.
- The token is kept in `localStorage`. That's simple, but readable by any script on the page, so `esc()` matters even more.
  The stronger alternative is an `HttpOnly` cookie with CSRF protection (see section 9).

### 4.16 Product photos (`app/images.py`)
A file upload is the most dangerous input a web app accepts, so a photo is never saved as it was sent:
- It is **opened by Pillow**: a file that isn't really an image (a script renamed `photo.jpg`, a corrupted file) is refused with a 400.
- **Limits:** 10 MB per file (read with a cap, so a huge upload can't fill the memory) and 50 megapixels (a "decompression bomb" is a tiny file that expands into a gigantic image).
- It is **re-encoded** as an 800 px JPEG: a 12 MB phone photo becomes about 80 KB, so the till stays fast on a slow connection.
  Re-encoding also **drops the EXIF metadata**, which on phones can include the GPS position where the photo was taken (the shop, or someone's home).
- The phone's rotation flag is applied first, so photos aren't sideways.
- The file gets a **random name chosen by the server**: an uploaded name like `../../app/main.py` can't overwrite anything.
- The old file is deleted only **after** the database points to the new one, so a crash in between never leaves a product pointing to a missing photo.
- Photos are served as static files from `/media/`; in Docker that folder is a volume, so photos survive updates.
- `tests/test_images.py` covers all of this, including a fake image and a photo carrying metadata.

### 4.17 Revendeurs: selling on credit (`app/routers/resellers.py`)
Other shops buy from MM Store and pay later. Three design decisions:
- **The debt is never stored.** What a reseller owes is always computed as *sum of their non-cancelled sales − sum of their payments*.
  A stored "balance" column would need updating in every place money moves, and one forgotten update makes it wrong forever.
  Computed, it can't drift, and cancelling a sale removes it from the debt with no extra code.
- **A credit sale is a normal sale** with `reseller_id` set and `payment_method = "credit"`, so stock, IMEIs, cancellations
  and reports all work exactly as before. Money handed over (at the till or later) is a separate `ResellerPayment` row,
  with who recorded it and how they paid.
- **Reseller prices** are an optional second price per product (`wholesale_price_centimes`). At the till, the "Revendeur" switch
  makes the server use it; like every price, it is copied onto the sale line, so changing it later never rewrites history.
The statement ("relevé") merges purchases and payments by date and computes the running balance, like a bank statement.

**Which purchases are still unpaid?** (`app/ledger.py`) A shop pays "1 500 DH" against its whole account, not against one
purchase, so payments are *allocated*: money paid at the till goes to that purchase first, everything else pays off the
oldest purchases first (FIFO, as accountants do). What's left on each purchase is shown with its products and IMEIs, and
how old it is (red after 30 days). It is computed every time, never stored, and a test checks that the amounts left on
all purchases always add up to the reseller's balance.
The data migration `0003` is also worth reading: it sorted existing accessories into the new groups from keywords in their names.

### 4.18 Running it for real (`deploy/`, `docker-compose.prod.yml`)
- **Caddy** sits in front of the app and gets the HTTPS certificate automatically. Only ports 80/443 (and SSH) are open;
  the database has no public port at all.
- **Login limits** (`app/ratelimit.py`): 5 wrong passwords on one account, or 20 from one address, in 15 minutes → wait.
  Counting by account stops guessing one password from many computers; counting by address stops one computer trying every account.
- **Backups** (`deploy/backup.sh`, nightly via cron): `pg_dump` in PostgreSQL's custom format plus the photos, written
  under a temporary name and renamed at the end so a half-written file never looks like a good backup; 30 days kept;
  optional copy to Google Drive with rclone. `restore.sh --check` proves a backup can really be restored without touching live data.
- **Updates** (`deploy/update.sh`): backup first, `git pull`, rebuild; migrations run when the app starts.
- In production the app refuses to start without a `SECRET_KEY`, and demo data can't be loaded.

### 4.19 Configuration, secrets and Docker
- Nothing secret is in the code: `SECRET_KEY` and the database password come from environment variables (`.env`, which is git-ignored).
- In the `Dockerfile`, requirements are installed before the code is copied, so Docker caches that layer. The app runs as a non-root user, and the container
  starts with `alembic upgrade head`, so the database schema is always up to date.
- `docker-compose.yml` runs PostgreSQL with a named volume (the data survives restarts) and a health check, and the API starts only once the database is ready.

---

## 5. Running it

**Local, without Docker** (uses a SQLite file):
```bash
python -m venv .venv && source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
alembic upgrade head
python -m app.cli create-admin --email gerant@boutique.ma --name "Gérant"
python -m app.cli seed-demo          # 10 demo products, seller account vendeur@demo.ma / vendeur123
uvicorn app.main:app --reload
```
- App: http://localhost:8000
- API docs, where you can try every endpoint: http://localhost:8000/docs (click "Authorize" and log in first)
- Tests: `pytest -v`

**Tests against PostgreSQL** (with Docker installed):
```bash
docker run -d --name pg-test -e POSTGRES_USER=boutique -e POSTGRES_PASSWORD=boutique -e POSTGRES_DB=boutique_test -p 5432:5432 postgres:16
TEST_DATABASE_URL=postgresql+psycopg://boutique:boutique@localhost:5432/boutique_test pytest -v
```

**Docker (production setup):**
```bash
cp .env.example .env     # set SECRET_KEY:  python -c "import secrets; print(secrets.token_urlsafe(48))"
docker compose up -d --build
docker compose exec api python -m app.cli create-admin --email gerant@boutique.ma --name "Gérant"
```

---

## 6. Putting it in a real store

1. **Hosting.** Pick one:
   - a managed platform (Render, Railway, Fly.io) with a managed PostgreSQL, which is easiest;
   - a small VPS running `docker compose`;
   - a PC in the shop running Docker, which works without internet but needs local backups.
2. **HTTPS is mandatory** on the internet, because passwords and tokens travel in every request. Managed platforms provide it.
   On a VPS, put Caddy or Nginx in front of the app.
3. **Backups.** Losing the database means losing the sales history. Schedule a daily `pg_dump` and copy it off the server.
   **Test a restore** at least once.
4. **Users.** Give each employee their own seller account, never a shared one, so the history shows who did what.
5. **Data entry.** Create the products, then use **Réception** to enter the stock. Phone IMEIs can be scanned straight into
   the text box, since a USB barcode scanner works like a keyboard.
6. **Legal.** Moroccan invoices have legal requirements (for example the store's ICE and tax identifiers). The receipt here is a
   simple ticket, so check with the store's accountant before using it as an official invoice.

---

## 7. Rebuild it yourself: a step-by-step plan

Don't copy-paste. Start from an empty folder and use this repository only to check your work when you're stuck.
Each stage ends with something running and tested.

1. **Hello FastAPI:** `/api/health`, run it with uvicorn, open `/docs`.
2. **Categories CRUD** with SQLAlchemy and SQLite: model, schemas, router, and 3 tests. (This is the pattern for everything else.)
3. **Products:** add the unique SKU (and the 409 when it's taken), PATCH with `exclude_unset`, search, and archiving.
4. **Stock:** `/restock` and `/adjust`, the `StockMovement` table, and the movements endpoint.
5. **Sales v1:** single product, conditional UPDATE, rollback, and tests for overselling and rollback.
6. **Sales v2:** multiple lines, line merging, discount, price snapshot.
7. **Auth:** users, bcrypt, login, JWT, `get_current_user`. Then protect every router.
8. **Roles:** `require_admin`, hiding the cost, sellers seeing only their own sales. Write the 403/404 tests first.
9. **IMEIs:** `SerialUnit`, restocking with IMEIs, selling by IMEI, lookup, and restoring on cancellation.
10. **Reports** with SQL aggregation and timezone-correct days.
11. **Alembic** plus the migration test; switch to PostgreSQL; then the concurrency test.
12. **Interface:** login, then the till, then the products view, then the rest.
13. **Docker and CI.**

**Extension ideas** (good for interviews: "what would you add next?"):
- Undo a payment entered by mistake (today: record the correction in the note and ask the manager)
- A Customers table, plus a warranty end date on each IMEI with "warranty valid?" shown in the lookup
- Suppliers and purchase orders
- Partial returns (one line, not the whole sale)
- Arabic translation with right-to-left layout
- PDF invoices
- Limit login attempts (rate limiting)
- A cash register report: opening float, cash counted at closing, difference

---

## 8. Interview questions you will get

**"Walk me through this project."**
> A full-stack inventory and point-of-sale system for a phone and electronics store in Morocco: FastAPI, PostgreSQL,
> JWT auth with two roles, per-unit IMEI tracking, an audit trail of every stock movement, and timezone-correct reports.
> 69 tests run in CI against PostgreSQL. The part I'm proudest of is preventing overselling under concurrency.

**"How do you prevent two cashiers from selling the same last phone?"**
> One atomic conditional UPDATE: `SET quantity = quantity - n WHERE id = ? AND quantity >= n`, then check the rowcount.
> I proved it with a test that fires 10 parallel requests on PostgreSQL. Exactly one succeeds. The naive
> read-then-write version oversold 10 times. Alternatives are `SELECT FOR UPDATE` or optimistic locking with a version column.

**"What happens if a sale fails halfway?"**
> It's one transaction. Any error triggers a rollback of the stock, the IMEI status, the movements and the sale row. There's a test for it.

**"Why store money as integers?"**
> Floating point can't represent 0.10 exactly, and rounding errors add up. Integer centimes are exact.

**"Why JWT, and what are its downsides?"**
> It's stateless and simple. The downside is that you can't revoke a token before it expires. I mitigate that by reloading the
> user on every request, so deactivation is immediate. Next steps would be short-lived access tokens plus refresh
> tokens, and HttpOnly cookies instead of localStorage.

**"How would you scale this to 50 stores?"**
> Add a `store_id` to products, stock, sales and users, and scope every query by it. Move per-store stock into its own
> table (product × store), add indexes on `(store_id, created_at)` for reports, and run several API instances behind
> a load balancer. The API is stateless, so that's easy. Heavy reports could later run on a read replica.

**"How do you change the database schema without losing data?"**
> Alembic migrations, reviewed and applied on deployment, plus a test that fails if the models and migrations drift apart.

**"What was the hardest bug?"**
> Pick a real one you hit while rebuilding it. One real example from this project: the `alembic` command couldn't import the app
> when run from the Docker image's start command, which would have crashed every deployment. It only showed up when testing from a clean
> install, and `prepend_sys_path = .` in `alembic.ini` fixed it. Another: Morocco's time zone change in September 2026.

Be ready to open any file and explain any line. If you can't explain a line, rebuild that part until you can.

---

## 9. Known limitations

- **No login rate limiting:** someone could try many passwords. Add a limiter (e.g. `slowapi`) or put it behind a proxy that limits requests.
- **Token in `localStorage`:** an XSS bug could steal it. `esc()` is used everywhere, but HttpOnly cookies would be stronger.
- **Whole-sale cancellation only:** no partial returns or exchanges yet.
- **Single store**, no offline mode: if the internet goes down, a cloud-hosted till stops.
- **Receipts are simple tickets**, not legally compliant invoices.
- **The browser formats dates:** a very old browser with outdated timezone data could show times one hour off. Reports aren't
  affected, because they're computed on the server.
- The Docker image wasn't built during development (no Docker daemon was available). Every step it runs was tested
  separately: clean install from `requirements.txt`, `alembic upgrade head`, and uvicorn startup. Run `docker compose up --build`
  once yourself before relying on it.
