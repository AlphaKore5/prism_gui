"""The Shop tab: products, orders, payments, settings.

Driven with a fake worker that answers from the demo platform, so nothing opens a socket, starts a thread or spins an event loop. Rules this file follows: no
processEvents()/exec()/QEventLoop (a dialog's exec is replaced by a method that returns), and nothing touches the real ~/.prism.
"""
from __future__ import annotations

import os
import sys
import tempfile
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import core_bridge  # noqa: F401,E402
from PySide6.QtWidgets import QApplication  # noqa: E402

_app = QApplication.instance() or QApplication([])

from addons.whatsapp import demo, demo_platform, demo_shop, readstate, ui  # noqa: E402
from whatsapp_fakes import last, routes, texts, worker  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="prism-wa-shop-")
    readstate.reset_cache()
    demo._state.clear()
    demo_platform._PAGE.clear()
    monkeypatch.setattr(demo_platform.time, "sleep", lambda _s: None)
    with mock.patch("paths.user_dir", lambda *p: os.path.join(tmp, *p)):
        yield
    demo._state.clear()
    demo_platform._PAGE.clear()


@pytest.fixture
def calls():
    return []


@pytest.fixture
def served(calls, monkeypatch):
    monkeypatch.setattr(ui, "PlatformWorker", worker(calls))
    return calls


@pytest.fixture
def page(served):
    from addons.whatsapp.shop_page import ShopPage
    p = ShopPage({})
    p.activate()
    return p


def buttons(widget) -> str:
    from PySide6.QtWidgets import QPushButton
    return " | ".join(b.text() for b in widget.findChildren(QPushButton))


def shop():
    return demo_shop._shop(demo_platform._state())


def never_open(monkeypatch, *classes):
    for cls in classes:
        monkeypatch.setattr(cls, "exec", lambda self: 0)


# ── the page ─────────────────────────────────────────────────────────────────

def test_the_page_opens_on_products_and_each_section_loads_what_it_shows(page, calls):
    assert "catalog/list" in routes(calls) and "Boundary wall panel" in texts(page._view("products"))
    for key, route in (("orders", "orders/list"), ("payments", "payments/dashboard"), ("settings", "commerce/config/get")):
        calls.clear()
        page.show_section(key)
        assert route in routes(calls), key
        assert page.stack.currentWidget() is page._view(key)


def test_the_shop_and_forms_are_tabs_of_the_workbench():
    from addons.whatsapp import workbench as W
    names = W._tab_names()
    assert len(names) == 10 and names[W._SHOP] == "Shop" and names[W._FORMS] == "Forms" and names.index("Settings") == len(names) - 1


# ── products ─────────────────────────────────────────────────────────────────

def test_products_show_their_price_sale_price_group_and_whether_they_are_in_the_meta_catalogue(page):
    t = texts(page._view("products"))
    assert "Rs 1,299.50" in t and "Rs 7,500.00 (was Rs 8,000.00)" in t and "Walls" in t and "Not available" in t and "Not sent to Meta yet" in t and "Code gate-1" in t


def test_searching_and_filtering_by_group_ask_the_server(page, calls):
    v = page._view("products")
    v.search.setText("gate")
    v.load()
    assert last(calls, "catalog/list")["q"] == "gate" and "Main gate" in texts(v) and "Boundary wall panel" not in texts(v)
    v.search.clear()
    v.group.setCurrentIndex(v.group.findData("Walls"))
    v.load()
    assert last(calls, "catalog/list")["category"] == "Walls"


def test_a_product_is_added_with_its_price_in_rupees_and_shows_up(page, calls):
    from addons.whatsapp.shop_products import ProductDialog
    d = ProductDialog(parent=page)
    d.name.setText("Garden light")
    d.price.setText("1,250.50")
    d.sale.setText("999")
    d.category.setText("Lights")
    d._go()
    sent = last(calls, "catalog/save")
    assert sent["name"] == "Garden light" and sent["price"] == "1,250.50" and sent["sale_price"] == "999" and sent["available"] is True and "id" not in sent
    row = [x for x in shop()["products"] if x["name"] == "Garden light"][0]
    assert row["price_paise"] == 125050 and row["sale_price_paise"] == 99900 and row["retailer_id"] == "garden-light"


def test_a_product_needs_a_name_and_a_sale_price_cannot_be_above_the_price(page, calls):
    from addons.whatsapp.shop_products import ProductDialog
    d = ProductDialog(parent=page)
    d._go()
    assert "Give the product a name" in d.error.text() and "catalog/save" not in routes(calls)
    d.name.setText("X")
    d.price.setText("100")
    d.sale.setText("200")
    d._go()
    assert "sale price cannot be more than the price" in d.error.text() and d.save_btn.isEnabled()
    d.price.setText("ten")
    d.sale.clear()
    d._go()
    assert "not a number" in d.error.text()


def test_editing_a_product_keeps_its_id_and_fills_the_form(page, calls):
    from addons.whatsapp.shop_products import ProductDialog
    gate = [x for x in shop()["products"] if x["retailer_id"] == "gate-1"][0]
    d = ProductDialog(dict(gate), page)
    assert d.name.text() == "Main gate" and d.price.text() == "8000.00" and d.sale.text() == "7500.00" and d.retailer.text() == "gate-1"
    d.name.setText("Main gate (steel)")
    d._go()
    assert last(calls, "catalog/save")["id"] == gate["id"] and gate["name"] == "Main gate (steel)"


def test_deleting_a_product_asks_first(page, calls, monkeypatch):
    v = page._view("products")
    gate = [x for x in shop()["products"] if x["retailer_id"] == "gate-1"][0]
    monkeypatch.setattr(ui, "confirm", lambda *a: False)
    v.delete(gate)
    assert "catalog/delete" not in routes(calls)
    monkeypatch.setattr(ui, "confirm", lambda *a: True)
    v.delete(gate)
    assert last(calls, "catalog/delete") == {"product_id": gate["id"]} and not any(x["retailer_id"] == "gate-1" for x in shop()["products"])


def test_a_spreadsheet_is_imported_and_the_rows_that_failed_are_named(page, calls):
    from addons.whatsapp.shop_products import ImportProductsDialog
    d = ImportProductsDialog(page)
    d._go()
    assert "Paste the spreadsheet" in d.report.text() and "catalog/import" not in routes(calls)
    d.text.setPlainText("id,title,price,category\nlamp-1,Lamp,450 INR,Lights\nbad-1,Broken,not a price,\n")
    d._go()
    assert "1 added" in d.report.text() and "row 3" in d.report.text() and d.imported and d.go.isEnabled()
    assert any(x["retailer_id"] == "lamp-1" and x["price_paise"] == 45000 for x in shop()["products"])


def test_the_meta_catalogue_is_read_and_written_with_the_counts_said_in_words(page, calls):
    v = page._view("products")
    v.pull()
    assert "From Meta: 1 new" in page.note.text() and any(x["retailer_id"] == "chair-9" for x in shop()["products"])
    v.push()
    assert "Sent 4 products to Meta" in page.note.text()


def test_the_catalogue_id_is_needed_before_talking_to_meta(page, calls):
    shop()["config"]["catalog_id"] = None
    page._view("products").pull()
    assert "add the catalogue id first" in page.note.text()


def test_a_product_is_sent_to_a_chat_only_once_someone_is_chosen(page, calls):
    from addons.whatsapp.shop_products import SendProductDialog
    gate = [x for x in shop()["products"] if x["retailer_id"] == "gate-1"][0]
    d = SendProductDialog(gate, page)
    d._go()
    assert "Choose who to send it to" in d.error.text() and "catalog/send" not in routes(calls)
    d.who.search.setText("Asha")
    d.who.search_now()
    assert d.who.results.count() > 1 and d.who.contact_id()
    d.message.setText("This one?")
    d._go()
    sent = last(calls, "catalog/send")
    assert sent["kind"] == "product" and sent["retailer_id"] == "gate-1" and sent["body"] == "This one?" and sent["contact_id"]


def test_the_whole_catalogue_can_be_offered_and_a_short_search_chooses_nobody(page, calls):
    from addons.whatsapp.shop_products import SendProductDialog
    d = SendProductDialog(None, page)
    assert d.what.currentData() == "catalog"
    d.who.search.setText("A")
    d.who.search_now()
    assert d.who.contact_id() == "" and "contacts/list" not in routes(calls)
    d.who.search.setText("zzzz-nobody")
    d.who.search_now()
    assert "Nobody found" in d.who.note.text()


def test_with_no_products_the_page_offers_to_add_one(page, calls):
    shop()["products"].clear()
    page._view("products").load()
    assert not page._view("products").empty.isHidden()


# ── orders ───────────────────────────────────────────────────────────────────

def test_orders_list_with_their_state_customer_total_and_where_they_came_from(page, calls):
    page.show_section("orders")
    t = texts(page._view("orders"))
    assert "Asha Patel" in t and "Ravi Shah" in t and "Kunal Desai" in t and "From WhatsApp cart" in t and "Waiting for payment" in t and "Paid" in t and "Cart" in t
    assert "Carts 1" in page._view("orders").counts.text() and "Paid 1" in page._view("orders").counts.text()


def test_orders_are_filtered_by_state_and_found_by_words(page, calls):
    v = page._view("orders")
    page.show_section("orders")
    from addons.whatsapp.shop_orders import _OrderRow
    v.status.setCurrentIndex(v.status.findData("paid"))
    v.load()
    assert last(calls, "orders/list")["status"] == "paid" and len(v.findChildren(_OrderRow)) == 1
    v.status.setCurrentIndex(0)
    v.search.setText("zzz")
    v.load()
    assert "No orders match" in texts(v)


def test_an_order_opens_with_its_items_totals_and_payments(page, calls):
    from addons.whatsapp.shop_orders import OrderDialog
    paid = [o for o in shop()["orders"] if o["status"] == "paid"][0]
    d = OrderDialog(demo_shop._order_view(shop(), demo_platform_state(), paid), page)
    t = texts(d)
    assert "2 × Boundary wall panel" in t and "1 × Main gate" in t and "Total" in t and "Payment link" in t and "UPI" in t and "Received" in t
    assert d.move_processing_btn and d.move_shipped_btn and not hasattr(d, "ask_btn")


def demo_platform_state():
    from addons.whatsapp import demo
    return demo._s()


def open_order(page, status):
    from addons.whatsapp.shop_orders import OrderDialog
    o = [x for x in shop()["orders"] if x["status"] == status][0]
    return OrderDialog(demo_shop._order_view(shop(), demo_platform_state(), o), page), o


def test_asking_the_customer_to_pay_makes_a_waiting_payment_and_the_order_waits(page, calls):
    d, o = open_order(page, "draft")
    d.ask(True)
    assert last(calls, "payments/request") == {"order_id": o["id"], "send": True}
    assert o["status"] == "awaiting_payment" and "Asked in the chat" in d.error.text() and d.changed
    assert "Waiting" in texts(d) and "Copy link" in buttons(d) and d.ask_btn.text() == "Ask again in the chat"


def test_a_payment_link_can_be_made_without_sending_it(page, calls):
    d, o = open_order(page, "draft")
    d.ask(False)
    assert last(calls, "payments/request")["send"] is False and "Link made" in d.error.text()


def test_checking_a_payment_with_the_gateway_marks_it_received(page, calls):
    d, o = open_order(page, "awaiting_payment")
    pay = d.order["payments"][0]
    d.check(pay)
    assert o["status"] == "paid" and "Received" in texts(d) and "payments/check" in routes(calls)


def test_a_paid_order_moves_along_and_the_customer_is_told(page, calls):
    d, o = open_order(page, "paid")
    d.message.setText("Courier: Blue Dart")
    d.move("shipped")
    assert last(calls, "orders/status") == {"order_id": o["id"], "status": "shipped", "note": "Courier: Blue Dart"} and o["status"] == "shipped"
    assert "The customer was told" in d.error.text() and d.message.text() == "" and d.move_completed_btn
    d.move("completed")
    assert o["status"] == "completed"


def test_an_order_cannot_skip_the_rules_and_the_reason_is_shown(page, calls):
    d, o = open_order(page, "draft")
    d.move("shipped")
    assert "cannot become" in d.error.text() and o["status"] == "draft"


def test_cancelling_an_order_asks_first_and_cancels_its_open_payment(page, calls, monkeypatch):
    d, o = open_order(page, "awaiting_payment")
    monkeypatch.setattr(ui, "confirm", lambda *a: False)
    d.cancel()
    assert "orders/cancel" not in routes(calls)
    monkeypatch.setattr(ui, "confirm", lambda *a: True)
    d.cancel()
    assert o["status"] == "cancelled" and all(p["status"] == "cancelled" for p in shop()["payments"] if p["order_id"] == o["id"])


def test_a_new_order_works_out_its_total_as_the_server_does(page, calls):
    from addons.whatsapp.shop_orders import NewOrderDialog
    cfg = shop()["config"]
    products = [x for x in shop()["products"] if x["available"]]
    d = NewOrderDialog(cfg, products, {"id": "k1", "name": "Asha Patel"}, page)
    line = d._all()[0]
    line.what.setCurrentIndex(line.what.findData("wall-6"))
    line.qty.setValue(4)
    # 4 x 1299.50 = 5198.00; tax 18% = 935.64; shipping 50.00 -> 6183.64
    assert "Total Rs 6,183.64" in d.summary.text() and "Tax Rs 935.64" in d.summary.text()
    d.discount.setText("198")
    assert "Total Rs 5,950.00" in d.summary.text()                                          # (5198 - 198) x 1.18 + 50
    d.shipping.setText("abc")
    assert d.summary.text() == ""


def test_an_order_can_include_something_that_is_not_in_the_catalogue(page, calls):
    from addons.whatsapp.shop_orders import NewOrderDialog
    d = NewOrderDialog(shop()["config"], [], {"id": "k1", "name": "Asha Patel"}, page)
    line = d._all()[0]
    line.what.setCurrentIndex(line.what.findData("__custom__"))
    assert not line.name.isHidden() and not line.price.isHidden()
    line.name.setText("Site survey")
    line.price.setText("1500")
    d.shipping.setText("0")
    d._go()
    sent = last(calls, "orders/create")
    assert sent["contact_id"] == "k1" and sent["items"] == [{"name": "Site survey", "price": "1500", "quantity": 1}]
    assert d.created["total_paise"] == 177000 and d.created["source"] == "agent"


def test_an_order_needs_an_item_and_lines_can_be_added_and_removed(page, calls):
    from addons.whatsapp.shop_orders import NewOrderDialog
    d = NewOrderDialog(shop()["config"], [x for x in shop()["products"]], {"id": "k1", "name": "Asha"}, page)
    d._go()
    assert "Add at least one item" in d.error.text() and "orders/create" not in routes(calls)
    d.add_line()
    assert len(d._all()) == 2
    d.remove_line(d._all()[0])
    d.remove_line(d._all()[0])
    assert len(d._all()) == 1                                           # the last line stays


def test_the_orders_page_makes_an_order_and_opens_it(page, calls, monkeypatch):
    from addons.whatsapp.shop_orders import NewOrderDialog, OrderDialog
    v = page._view("orders")
    page.show_section("orders")

    def fake_exec(self):
        line = self._all()[0]
        line.what.setCurrentIndex(line.what.findData("gate-1"))
        self.created = None
        self._go()
        return 1
    monkeypatch.setattr(NewOrderDialog, "exec", fake_exec)
    monkeypatch.setattr(OrderDialog, "exec", lambda self: 0)
    v.new({"id": "k2", "name": "Ravi Patel"})
    assert "Order " in page.note.text() and "made" in page.note.text() and last(calls, "orders/create")["contact_id"] == "k2"


# ── payments ─────────────────────────────────────────────────────────────────

def test_the_money_figures_are_shown_in_rupees_from_whole_paise(page, calls):
    page.show_section("payments")
    v = page._view("payments")
    d = demo_shop._dashboard(shop())
    assert v.k_in.value.text() == "Rs {:,.2f}".format(d["received_paise"] / 100.0) and v.k_wait.value.text() == "1" and v.k_rate.value.text() == "100.0%"
    assert "UPI" in v.methods.text()
    assert len(v.chart._days) == 1


def test_people_whose_payment_did_not_go_through_are_listed_with_a_way_to_the_order(page, calls):
    page.show_section("payments")
    v = page._view("payments")
    t = texts(v)
    assert "Ravi Shah" in t and "payment still open" in t and "Open order" in buttons(v)


def test_a_waiting_payment_can_be_checked_and_a_received_one_refunded_in_part(page, calls, monkeypatch):
    from addons.whatsapp.shop_orders import RefundDialog
    page.show_section("payments")
    v = page._view("payments")
    waiting = [p for p in shop()["payments"] if p["status"] == "pending"][0]
    v.check(waiting)
    assert waiting["status"] == "captured"
    got = [p for p in shop()["payments"] if p["status"] == "captured"][0]
    d = RefundDialog(demo_shop._payment_view(shop(), demo_platform_state(), got), page)
    d.amount.setText("100")
    d.reason.setText("Damaged")
    d._go(False)
    sent = last(calls, "payments/refund")
    assert sent["amount"] == "100" and sent["reason"] == "Damaged" and sent["record_only"] is False
    assert got["status"] == "partially_refunded" and got["refunded_paise"] == 10000


def test_a_refund_cannot_be_more_than_what_is_left_and_says_so_before_asking(page, calls):
    from addons.whatsapp.shop_orders import RefundDialog
    got = [p for p in shop()["payments"] if p["status"] == "captured"][0]
    d = RefundDialog(demo_shop._payment_view(shop(), demo_platform_state(), got), page)
    d.amount.setText("99999999")
    d._go(False)
    assert "Give back between 0.01 and" in d.error.text() and "payments/refund" not in routes(calls)
    d.amount.setText("abc")
    d._go(False)
    assert "not a number" in d.error.text()


def test_a_refund_made_elsewhere_can_be_recorded_when_prism_cannot_send_it(page, calls):
    from addons.whatsapp.shop_orders import RefundDialog
    shop()["config"]["razorpay_secret_set"] = False
    got = [p for p in shop()["payments"] if p["status"] == "captured"][0]
    d = RefundDialog(demo_shop._payment_view(shop(), demo_platform_state(), got), page)
    d._go(False)
    assert "Prism cannot send this refund" in d.error.text() and got["refunded_paise"] == 0
    d._go(True)
    assert got["status"] == "refunded" and last(calls, "payments/refund")["record_only"] is True


# ── settings ─────────────────────────────────────────────────────────────────

def test_the_settings_show_what_is_saved_and_never_a_secret(page, calls):
    page.show_section("settings")
    v = page._view("settings")
    assert v.catalog_id.text() == "5551234567" and v.tax.text() == "18" and v.shipping.text() == "50.00" and v.gateway.currentData() == "razorpay" and v.key_id.text().startswith("rzp_test_")
    assert v.key_secret.text() == "" and "Saved" in v.key_secret.placeholderText() and v.ready.text() == "Ready to take payments"
    assert not v.razorpay_box.isHidden() and v.meta_box.isHidden() and v.hook_url.text().endswith("/v1/whatsapp/pay/razorpay/demo-workspace")


def test_changing_the_way_of_paying_shows_its_own_fields(page, calls):
    page.show_section("settings")
    v = page._view("settings")
    v.gateway.setCurrentIndex(v.gateway.findData("meta"))
    assert v.razorpay_box.isHidden() and not v.meta_box.isHidden()
    v.gateway.setCurrentIndex(v.gateway.findData("none"))
    assert v.razorpay_box.isHidden() and v.meta_box.isHidden()


def test_secrets_are_sent_only_when_typed(page, calls):
    page.show_section("settings")
    v = page._view("settings")
    assert "razorpay_secret" not in v.payload() and "razorpay_webhook_secret" not in v.payload()
    v.key_secret.setText("new-secret-value")
    v.hook_secret.setText("hook-secret-value")
    assert v.payload()["razorpay_secret"] == "new-secret-value" and v.payload()["razorpay_webhook_secret"] == "hook-secret-value"


def test_saving_the_settings_says_whether_customers_can_pay_yet(page, calls):
    page.show_section("settings")
    v = page._view("settings")
    v.tax.setText("5")
    v.save()
    assert shop()["config"]["tax_percent"] == 5.0 and v.note.text() == "Saved." and v.save_btn.isEnabled()
    v.gateway.setCurrentIndex(v.gateway.findData("meta"))
    v.payment_config.clear()
    v.save()
    assert "Customers can't be asked to pay yet" in v.note.text() and v.ready.text() == "Not ready to take payments"


@pytest.mark.parametrize("field,value,fragment", [("tax", "120", "between 0 and 100"), ("currency", "12", "three letters"), ("key_id", "key_123", "looks like rzp_"),
                                                  ("catalog_id", "abc", "is a number"), ("expiry", "0", "1 hour to 30 days")])
def test_a_wrong_setting_is_refused_in_words_and_the_save_button_comes_back(page, calls, field, value, fragment):
    page.show_section("settings")
    v = page._view("settings")
    getattr(v, field).setText(value)
    v.save()
    assert fragment in v.note.text() and v.save_btn.isEnabled() and v.note.tone == "error"


def test_the_catalogues_on_the_number_can_be_found_and_picked(page, calls):
    page.show_section("settings")
    v = page._view("settings")
    v.find_catalogs()
    assert v.found.count() == 2 and not v.found.isHidden()
    v.found.setCurrentIndex(1)
    v._picked()
    assert v.catalog_id.text() == "5559876543" and v.catalog_name.text() == "Old catalogue"


def test_the_chat_buttons_are_applied_to_the_number(page, calls):
    page.show_section("settings")
    v = page._view("settings")
    v.cart.setChecked(True)
    v.save_visibility()
    assert last(calls, "catalog/set_visibility") == {"catalog_visible": True, "cart_enabled": True} and shop()["visible"]["cart_enabled"] is True


# ── from a chat or a contact ─────────────────────────────────────────────────

def test_the_chat_profile_offers_a_new_order_and_a_form_for_that_person(served):
    from addons.whatsapp.profile_panel import ProfilePanel
    heard = {"order": [], "form": []}
    p = ProfilePanel()
    p.startOrder.connect(lambda c: heard["order"].append(c))
    p.sendForm.connect(lambda c: heard["form"].append(c))
    p.load("k1")
    p.order_btn.click()
    p.form_btn.click()
    assert heard["order"][0]["id"] == "k1" and heard["form"][0]["id"] == "k1" and heard["order"][0]["name"] == "Asha Patel"


def test_a_new_order_from_a_chat_opens_the_shop_with_that_person_chosen(served, calls, monkeypatch):
    from addons.whatsapp import workbench as W
    from addons.whatsapp.shop_orders import NewOrderDialog, OrderDialog
    seen = {}
    monkeypatch.setattr(NewOrderDialog, "exec", lambda self: (seen.setdefault("who", self.who.contact_id()), 0)[1])
    wb = W.WhatsAppWorkbench({})
    wb._order_for({"id": "k2", "name": "Ravi Shah"})
    assert wb._current == W._SHOP and seen["who"] == "k2"
