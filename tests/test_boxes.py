from app.utils.boxes import (
    DEFAULT_BOXES,
    get_box_by_digit,
    get_box_by_slug,
    get_box_notify_phone_numbers,
    get_default_box,
    list_boxes,
    update_box,
)


def test_seed_creates_four_default_boxes(app):
    boxes = list_boxes()
    assert [b["slug"] for b in boxes] == [b["slug"] for b in DEFAULT_BOXES]
    assert [b["extension_digit"] for b in boxes] == ["1", "2", "3", "4"]


def test_get_box_by_digit_returns_enabled_box(app):
    assert get_box_by_digit("2")["slug"] == "cody"
    # An unmapped digit yields nothing.
    assert get_box_by_digit("9") is None


def test_get_box_by_digit_skips_disabled(app):
    ryan = get_box_by_slug("ryan")
    update_box(ryan["id"], enabled=0)
    assert get_box_by_digit("3") is None


def test_disabled_box_left_out_of_menu(app):
    cory = get_box_by_slug("cory")
    update_box(cory["id"], enabled=0)
    slugs = [b["slug"] for b in list_boxes(enabled_only=True)]
    assert "cory" not in slugs


def test_default_box_is_family(app):
    assert get_default_box()["slug"] == "family"


def test_box_notify_numbers_filters_invalid(app):
    cody = get_box_by_slug("cody")
    update_box(cody["id"], notify_phone_numbers="+15551112222,not-a-number")
    numbers = get_box_notify_phone_numbers(get_box_by_slug("cody"))
    assert numbers == ["+15551112222"]


def test_box_edit_via_admin(auth_client):
    cody = get_box_by_slug("cody")
    resp = auth_client.post(
        f"/admin/boxes/{cody['id']}/edit",
        data={
            "display_name": "Cody M.",
            "extension_digit": "2",
            "voicemail_prompt": "Leave Cody a message.",
            "voicemail_thanks": "",
            "notify_phone_numbers": "+15551112222",
            "enabled": "y",
        },
    )
    assert resp.status_code == 302
    updated = get_box_by_slug("cody")
    assert updated["display_name"] == "Cody M."
    assert updated["voicemail_prompt"] == "Leave Cody a message."
    assert updated["notify_phone_numbers"] == "+15551112222"


def test_box_edit_rejects_duplicate_digit(auth_client):
    cody = get_box_by_slug("cody")
    # Digit 1 already belongs to Family.
    resp = auth_client.post(
        f"/admin/boxes/{cody['id']}/edit",
        data={
            "display_name": "Cody",
            "extension_digit": "1",
            "voicemail_prompt": "",
            "voicemail_thanks": "",
            "notify_phone_numbers": "",
            "enabled": "y",
        },
    )
    assert resp.status_code == 200  # re-renders with an error
    assert get_box_by_slug("cody")["extension_digit"] == "2"
