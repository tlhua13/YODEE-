/** @odoo-module */

import { _t } from "@web/core/l10n/translation";
import { NumberPopup } from "@point_of_sale/app/utils/input_popups/number_popup";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { patch } from "@web/core/utils/patch";

patch(ControlButtons.prototype, {
    async clickDirectDiscountProduct() {
        const order = this.pos.get_order();
        if (!order) return;

        const selectedLine = order.get_selected_orderline();
        if (!selectedLine) return;

        this.dialog.add(NumberPopup, {
            title: _t("Giảm giá sản phẩm (VND)"),
            startingValue: selectedLine.direct_discount_amount || 0,
            getPayload: (num) => {
                const discountAmount = this.env.utils.parseValidFloat(num.toString());
                if (discountAmount < 0) return;

                // Get total price with tax before any discount
                const totalInclBeforeDiscount = selectedLine.get_all_prices().priceWithTaxBeforeDiscount;
                if (totalInclBeforeDiscount <= 0) return;

                // discount % = vnd / total_incl * 100
                // e.g. 100,000 + 8% VAT = 108,000. Enter 5000 → 5000/108000*100 = 4.6296%
                // Odoo: 100,000 * (1 - 4.6296%) * 1.08 = 103,000
                const discountPc = Math.min(100, (discountAmount / totalInclBeforeDiscount) * 100);
                selectedLine.discount = discountPc;
                selectedLine.direct_discount_amount = discountAmount;
            },
        });
    },
});
