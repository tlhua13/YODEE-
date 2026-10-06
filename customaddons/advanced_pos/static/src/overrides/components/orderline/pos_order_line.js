/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { Orderline } from "@point_of_sale/app/generic_components/orderline/orderline";
import { formatCurrency } from "@point_of_sale/app/models/utils/currency";

// Register new keys in Orderline props shape
Orderline.props.line.shape.direct_discount_amount = { type: String, optional: true };
Orderline.props.line.shape.total_before_discount = { type: String, optional: true };

patch(PosOrderline.prototype, {
    getDisplayData() {
        const data = super.getDisplayData(...arguments);
        if (this.direct_discount_amount) {
            const totalIncl = this.get_all_prices().priceWithTaxBeforeDiscount;
            data.direct_discount_amount = formatCurrency(this.direct_discount_amount, this.currency);
            data.total_before_discount = formatCurrency(totalIncl, this.currency);
        }
        return data;
    },

    set_quantity(quantity, keep_price) {
        const result = super.set_quantity(quantity, keep_price);
        // Recalculate discount % to keep VND amount fixed when qty changes
        if (this.direct_discount_amount) {
            const totalInclBeforeDiscount = this.get_all_prices().priceWithTaxBeforeDiscount;
            if (totalInclBeforeDiscount > 0) {
                this.discount = Math.min(100, (this.direct_discount_amount / totalInclBeforeDiscount) * 100);
            }
        }
        return result;
    },
});
