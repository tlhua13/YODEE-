import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { patch } from "@web/core/utils/patch";

patch(PosOrder.prototype, {
    get getNotiExpiryPoint() {
        const partner = this.get_partner();
        return partner?.noti_expiry || "";
    },
});