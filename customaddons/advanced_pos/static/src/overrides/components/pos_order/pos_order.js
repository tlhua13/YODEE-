/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { PosOrder } from "@point_of_sale/app/models/pos_order";

patch(PosOrder.prototype, {
    export_for_printing() {
        // gọi logic gốc
        const result = super.export_for_printing(...arguments);

        // thêm field mới
        const today = new Date();
        result.date_pos = today.toLocaleDateString("vi-VN");

        return result;
    },
});