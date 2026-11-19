import io

from PIL import Image

from app.images import PRODUCTS_DIR


def photo_bytes(fmt="JPEG", size=(1600, 1200), color=(40, 60, 200), mode="RGB"):
    buffer = io.BytesIO()
    Image.new(mode, size, color).save(buffer, fmt)
    return buffer.getvalue()


def upload(client, headers, product_id, data, name="photo.jpg", content_type="image/jpeg"):
    return client.post(f"/api/products/{product_id}/image", headers=headers,
                       files={"file": (name, data, content_type)})


def test_upload_photo_is_resized_and_served(client, admin, seller, make_product):
    product = make_product()
    response = upload(client, admin, product["id"], photo_bytes())
    assert response.status_code == 200
    url = response.json()["image_url"]
    assert url.startswith("/media/products/") and url.endswith(".jpg")

    served = client.get(url)                       # anyone can load the picture file itself
    assert served.status_code == 200
    with Image.open(io.BytesIO(served.content)) as image:
        assert max(image.size) == 800              # shrunk from 1600 x 1200
    # sellers see the photo in product lists too
    assert client.get(f"/api/products/{product['id']}", headers=seller).json()["image_url"] == url


def test_transparent_png_is_accepted(client, admin, make_product):
    product = make_product()
    data = photo_bytes("PNG", (300, 300), (0, 0, 0, 0), mode="RGBA")
    assert upload(client, admin, product["id"], data, "logo.png", "image/png").status_code == 200


def test_replacing_a_photo_deletes_the_old_file(client, admin, make_product):
    product = make_product()
    first = upload(client, admin, product["id"], photo_bytes()).json()["image_url"].rsplit("/", 1)[1]
    second = upload(client, admin, product["id"], photo_bytes(color=(200, 0, 0))).json()["image_url"].rsplit("/", 1)[1]
    assert first != second
    assert not (PRODUCTS_DIR / first).exists() and (PRODUCTS_DIR / second).exists()


def test_remove_photo(client, admin, make_product):
    product = make_product()
    name = upload(client, admin, product["id"], photo_bytes()).json()["image_url"].rsplit("/", 1)[1]
    response = client.delete(f"/api/products/{product['id']}/image", headers=admin)
    assert response.json()["image_url"] is None
    assert not (PRODUCTS_DIR / name).exists()


def test_non_image_files_are_refused(client, admin, make_product):
    product = make_product()
    fake = b"<?php system($_GET['cmd']); ?>"
    response = upload(client, admin, product["id"], fake, "photo.jpg", "image/jpeg")   # lying name and type
    assert response.status_code == 400
    assert "photo" in response.json()["detail"]
    truncated = photo_bytes()[:200]
    assert upload(client, admin, product["id"], truncated).status_code == 400


def test_too_large_file_is_refused(client, admin, make_product):
    product = make_product()
    assert upload(client, admin, product["id"], b"0" * (10 * 1024 * 1024 + 10)).status_code == 413


def test_sellers_cannot_change_photos(client, seller, make_product):
    product = make_product()
    assert upload(client, seller, product["id"], photo_bytes()).status_code == 403


def test_phone_photo_metadata_is_removed(client, admin, make_product):
    """Phone photos can contain the GPS position of the shop or the owner's home."""
    product = make_product()
    buffer = io.BytesIO()
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"          # camera make
    exif[0x0112] = 6                     # orientation: rotate 90°
    Image.new("RGB", (400, 200), (10, 10, 10)).save(buffer, "JPEG", exif=exif.tobytes())
    url = upload(client, admin, product["id"], buffer.getvalue()).json()["image_url"]
    with Image.open(io.BytesIO(client.get(url).content)) as image:
        assert image.size == (200, 400)          # turned upright
        assert dict(image.getexif()) == {}       # no metadata left
