"""The step cards added after the first flow builder: a file, a map pin, asking for a pin, telling another system, telling Meta.

They are a mixin for StepCard (flow_steps.py): each `_build_<kind>` uses the card's own `_field`, `_next` and `_timeout`, so a new
kind of step is one method here and one line in flow_model.py — nothing else needs to know it exists.
"""
from __future__ import annotations

import re

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QWidget

import i18n
import theme
from addons.whatsapp import flow_model as M
from addons.whatsapp import ui
from addons.whatsapp.flow_fields import line, text_edit
from addons.whatsapp.media_lib import AssetField
from widgets import controls as C

NUMBER = re.compile(r"^-?\d{1,3}(\.\d+)?$")


def number_or_none(text: str):
    """A coordinate typed by a person: a number, or nothing yet (never half a number)."""
    t = (text or "").strip()
    if not t:
        return None
    try:
        return float(t) if NUMBER.match(t) else None
    except ValueError:
        return None


def pin_from_text(text: str):
    """"22.3072, 73.1812" (what Google Maps copies) -> (22.3072, 73.1812), or None."""
    m = re.match(r"^\s*(-?\d{1,3}(?:\.\d+)?)\s*[,;\s]\s*(-?\d{1,3}(?:\.\d+)?)\s*$", text or "")
    return (float(m.group(1)), float(m.group(2))) if m else None


class MoreSteps:
    """Mixed into StepCard."""

    def _build_media(self):
        node = self.node
        kinds = QComboBox()
        kinds.setMinimumHeight(34)
        for k in M.MEDIA_KINDS:
            kinds.addItem(M.media_kind_name(k), k)
        kinds.setCurrentIndex(max(kinds.findData(node.get("kind", "image")), 0))
        self._field(i18n.t("What kind of file"), kinds)
        holder = QHBoxLayout()
        self.asset = AssetField(kinds=[node.get("kind", "image")], empty_text=i18n.t("Choose a file from your Media Library"))
        holder.addWidget(self.asset, 1)
        self._field(i18n.t("The file"), holder, i18n.t("Pictures up to 5 MB; videos, voice notes and documents up to 16 MB."))
        self.asset.set_asset_id(node.get("asset_id") or None)

        def chosen():
            node["asset_id"] = self.asset.asset_id() or ""
            a = self.asset.asset()
            if a and a.get("kind") in M.MEDIA_KINDS and a.get("kind") != node.get("kind"):       # the file decides what kind it is
                node["kind"] = a["kind"]
                kinds.setCurrentIndex(max(kinds.findData(a["kind"]), 0))
                self.asset.kinds = (a["kind"],)
            self.changed.emit()
        self.asset.changed.connect(chosen)

        caption = text_edit(node.get("caption"), self._set("caption"), 60, i18n.t("Words under the file (optional)"), i18n.t("Words under the file"))
        self.caption_box = ui.field(i18n.t("Words under it"), caption, i18n.t("{{first_name}} and the other blanks are filled in. A voice note cannot have words."))
        self.body.addWidget(self.caption_box)
        self.caption_box.setVisible(node.get("kind") != "audio")

        def kind_chosen(*_):
            node["kind"] = kinds.currentData()
            self.asset.kinds = (node["kind"],)
            if node["kind"] == "audio":
                node.pop("caption", None)
            self.caption_box.setVisible(node["kind"] != "audio")
            self.changed.emit()
        kinds.activated.connect(kind_chosen)
        self._next()

    def _build_location_request(self):
        self._field(i18n.t("What to ask"), text_edit(self.node.get("text"), self._set("text"), 72, i18n.t("Please share your location so we can find the nearest branch."),
                                                      i18n.t("What to ask")),
                    i18n.t("WhatsApp shows a Send location button under it. The pin is kept for the next steps as {{var.location_lat}} and {{var.location_lng}}."))
        self._next("next", i18n.t("When they share it"))
        self._next("fallback_next", i18n.t("If they write something else"))
        self._timeout()

    def _build_send_location(self):
        node = self.node

        def coord(key):
            def fn(text):
                v = number_or_none(text)
                node[key] = v
                self.changed.emit()
            return fn
        row = QHBoxLayout()
        row.setSpacing(theme.SPACE_2)
        lat = line("" if node.get("latitude") is None else str(node["latitude"]), coord("latitude"), i18n.t("Latitude, e.g. 22.3072"), i18n.t("Latitude"))
        lng = line("" if node.get("longitude") is None else str(node["longitude"]), coord("longitude"), i18n.t("Longitude, e.g. 73.1812"), i18n.t("Longitude"))
        row.addWidget(lat)
        row.addWidget(lng)
        self._field(i18n.t("Where"), row, i18n.t("In Google Maps, right-click a place and click the numbers to copy them. Paste both here and they are split for you."))

        def pasted(text):
            pin = pin_from_text(text)
            if pin:
                lat.setText(str(pin[0]))
                lng.setText(str(pin[1]))
        lat.textChanged.connect(pasted)
        self._field(i18n.t("Name of the place"), line(node.get("name"), self._set("name"), i18n.t("Our showroom"), i18n.t("Name of the place")))
        self._field(i18n.t("Address"), line(node.get("address"), self._set("address"), i18n.t("12 Alkapuri Road, Vadodara"), i18n.t("Address")))
        self._next()

    def _build_webhook(self):
        node = self.node
        row = QHBoxLayout()
        method = QComboBox()
        method.setMinimumHeight(34)
        method.addItems(["POST", "GET"])
        method.setCurrentText(node.get("method", "POST"))
        method.activated.connect(lambda _i: (node.__setitem__("method", method.currentText()), self.changed.emit()))
        row.addWidget(method)
        row.addWidget(line(node.get("url"), self._set("url"), "https://…", i18n.t("Address")), 1)
        self._field(i18n.t("Send to"), row, i18n.t("Your server gets the details and the flow carries on at once — it never waits for the answer, and a failure does not stop it."))
        headers = "\n".join("%s: %s" % (k, v) for k, v in (node.get("headers") or {}).items())
        self._field(i18n.t("Headers"), text_edit(headers, lambda t: (node.__setitem__("headers", dict((ln.split(":", 1)[0].strip(), ln.split(":", 1)[1].strip())
                                                                                                    for ln in t.splitlines() if ":" in ln)), self.changed.emit()),
                                                 60, "Authorization: Bearer …", i18n.t("Headers")))
        self._field(i18n.t("What to send"), text_edit(node.get("body", ""), lambda t: (node.__setitem__("body", t) if t else node.pop("body", None), self.changed.emit()),
                                                      72, '{"name": "{{name}}", "phone": "{{mobile}}", "answer": "{{var.city}}"}', i18n.t("What to send")),
                    i18n.t("{{name}}, {{mobile}}, {{attr.City}} and {{var.x}} are filled in for each customer."))
        self._next()

    def _build_capi_event(self):
        node = self.node
        event = QComboBox()
        event.setMinimumHeight(34)
        for e in M.CAPI_EVENTS:
            event.addItem(e, e)
        event.setCurrentIndex(max(event.findData(node.get("event", "Lead")), 0))
        event.activated.connect(lambda _i: (node.__setitem__("event", event.currentData()), self.changed.emit()))
        self._field(i18n.t("What happened"), event, i18n.t("Meta only credits it to an ad when the customer came from that ad's click. Anyone else is left alone."))
        row = QHBoxLayout()
        row.setSpacing(theme.SPACE_2)
        value = line("" if node.get("value") is None else str(node["value"]), lambda t: (node.__setitem__("value", t.strip()) if t.strip() else node.pop("value", None), self.changed.emit()),
                     i18n.t("Worth (optional), e.g. 25000 or {{var.amount}}"), i18n.t("Worth"))
        currency = QLineEdit(node.get("currency", "INR"))
        currency.setMaxLength(3)
        currency.setMaximumWidth(80)
        currency.setMinimumHeight(34)
        currency.setAccessibleName(i18n.t("Currency"))
        currency.textChanged.connect(lambda t: (node.__setitem__("currency", t.strip().upper()) if t.strip() else node.pop("currency", None), self.changed.emit()))
        row.addWidget(value, 1)
        row.addWidget(currency)
        self._field(i18n.t("Worth"), row, i18n.t("A number or a {{var.name}} the flow saved, and a three-letter currency like INR."))
        self._next()

    def _build_send_products(self):
        node = self.node
        mode = QComboBox()
        mode.setMinimumHeight(34)
        mode.addItem(i18n.t("One product"), "product")
        mode.addItem(i18n.t("A list of products"), "products")
        mode.addItem(i18n.t("The whole catalogue"), "catalog")
        mode.setCurrentIndex(max(mode.findData(node.get("mode", "catalog")), 0))
        self._field(i18n.t("What to show"), mode)
        products = self.ctx.products()
        self.product_box = QWidget()
        pb = QHBoxLayout(self.product_box)
        pb.setContentsMargins(0, 0, 0, 0)
        one = QComboBox()
        one.setMinimumHeight(34)
        one.setAccessibleName(i18n.t("Product"))
        one.addItem(i18n.t("Choose a product"), "")
        for p in products:
            one.addItem(p["name"], p["retailer_id"])
        if node.get("retailer_id") and one.findData(node["retailer_id"]) < 0:
            one.addItem(node["retailer_id"], node["retailer_id"])
        one.setCurrentIndex(max(one.findData(node.get("retailer_id") or ""), 0))
        one.activated.connect(lambda _i: (node.__setitem__("retailer_id", one.currentData()), self.changed.emit()))
        pb.addWidget(one, 1)
        self.body.addWidget(ui.field(i18n.t("Which product"), self.product_box))
        self.product_one = one
        self.list_box = text_edit("\n".join(node.get("retailer_ids") or []), lambda t: (node.__setitem__("retailer_ids", [x.strip() for x in t.splitlines() if x.strip()]), self.changed.emit()), 90,
                                  "wall-6\ngate-1", i18n.t("Product codes"))
        hint = i18n.t("One product code per line (up to 30). Codes are shown on each product in the Shop tab.")
        self.list_field = ui.field(i18n.t("Which products"), self.list_box, hint)
        self.body.addWidget(self.list_field)

        def shown():
            m = node.get("mode", "catalog")
            self.product_box.parentWidget().setVisible(m == "product")
            self.list_field.setVisible(m == "products")
        mode.activated.connect(lambda _i: (node.__setitem__("mode", mode.currentData()), shown(), self.changed.emit()))
        shown()
        self._field(i18n.t("Words with it"), text_edit(node.get("text"), self._set("text"), 60, i18n.t("Have a look at these."), i18n.t("Words with the products")),
                    i18n.t("{{first_name}} and the other blanks are filled in."))
        self._next()

    def _build_send_form(self):
        node = self.node
        combo = QComboBox()
        combo.setMinimumHeight(34)
        combo.setAccessibleName(i18n.t("Form"))
        combo.addItem(i18n.t("Choose a form"), "")
        for f in self.ctx.forms():
            combo.addItem(f["name"], f["id"])
        if node.get("form_id") and combo.findData(node["form_id"]) < 0:
            combo.addItem(i18n.t("A form that is not published"), node["form_id"])
        combo.setCurrentIndex(max(combo.findData(node.get("form_id") or ""), 0))
        combo.activated.connect(lambda _i: (node.__setitem__("form_id", combo.currentData()), self.changed.emit()))
        self._field(i18n.t("Which form"), combo, i18n.t("Only published forms are listed. Make and publish forms in the Forms tab."))
        self.form_combo = combo
        self._field(i18n.t("Words above the button"), text_edit(node.get("text"), self._set("text"), 60, i18n.t("Please fill in this short form."), i18n.t("Words above the button")))
        self._field(i18n.t("Button words"), line(node.get("button"), self._set("button"), i18n.t("Open form"), i18n.t("Button words")))
        self._next()

    def _build_request_payment(self):
        self.body.addWidget(C.label(i18n.t("Asks the customer to pay the cart they just sent from your catalogue, with the way of paying you chose in the Shop tab."), level="SUPPORT",
                                    colour=theme.NEUTRAL[600], wrap=True))
        self._field(i18n.t("If there is no cart"), text_edit(self.node.get("empty_text"), self._set("empty_text"), 60, i18n.t("Send me your cart first and I will ask for payment."),
                                                              i18n.t("If there is no cart")), i18n.t("What to say when the customer has not sent a cart. The flow carries on after it."))
        self._next()

    # ── the API step's test button ───────────────────────────────────────────
    def _api_test_row(self):
        row = QHBoxLayout()
        self.api_test_btn = C.button(i18n.t("Try this call"), "secondary", small=True, on_click=self._try_call)
        row.addWidget(self.api_test_btn)
        row.addStretch(1)
        box = QWidget()
        box.setLayout(row)
        self.body.addWidget(box)
        self.api_result = C.label("", level="META", colour=theme.NEUTRAL[700], wrap=True)
        self.api_result.setVisible(False)
        self.body.addWidget(self.api_result)

    def _try_call(self):
        self.api_test_btn.setEnabled(False)
        self.api_result.setVisible(True)
        self.api_result.setText(i18n.t("Calling…"))
        ui.call(self, "flows/test_request", {"node": {k: v for k, v in self.node.items() if k in ("method", "url", "headers", "body", "save")}},
                done=self._call_done, failed=lambda m, _d: self._call_failed(m))

    def _call_failed(self, message: str):
        self.api_test_btn.setEnabled(True)
        self.api_result.setStyleSheet("color: %s; font-size: 12px;" % theme.ERR_INK)
        self.api_result.setText(message)

    def _call_done(self, reply: dict):
        self.api_test_btn.setEnabled(True)
        if reply.get("error"):
            self._call_failed(reply["error"])
            return
        good = bool(reply.get("ok"))
        self.api_result.setStyleSheet("color: %s; font-size: 12px;" % (theme.OK_INK if good else theme.ERR_INK))
        lines = [i18n.t("It answered {n}.").format(n=reply.get("status")) if good else i18n.t("It answered {n} — the flow would take the “If it fails” path.").format(n=reply.get("status"))]
        if not reply.get("json"):
            lines.append(i18n.t("The answer is not JSON, so nothing can be kept from it."))
        for name, found in (reply.get("kept") or {}).items():
            lines.append(("%s = %s" % (name, found)) if found is not None else i18n.t("{n}: not found in the answer").format(n=name))
        body = (reply.get("body") or "").strip().replace("\n", " ")
        if body:
            lines.append(body[:300] + ("…" if len(body) > 300 else ""))
        self.api_result.setText("\n".join(lines))
