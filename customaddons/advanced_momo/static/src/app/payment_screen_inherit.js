/** @odoo-module **/

import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { MomoQRDisplay } from "@advanced_momo/app/momo_qr_display";
import { patch } from "@web/core/utils/patch";

PaymentScreen.components = {
    ...PaymentScreen.components,
    MomoQRDisplay,
};

patch(PaymentScreen.prototype, {
    async addNewPaymentLine(paymentMethod) {
        if (
            paymentMethod.use_payment_terminal === "momo" &&
            !this.currentOrder.get_partner()
        ) {
            await this._setMomoDefaultPartner(paymentMethod);
        }
        return await super.addNewPaymentLine(paymentMethod);
    },

    async _setMomoDefaultPartner(paymentMethod) {
        const defaultPartnerData = paymentMethod.momo_default_partner_id;
        if (!defaultPartnerData) {
            return;
        }
        let partnerId;
        if (Array.isArray(defaultPartnerData)) {
            partnerId = defaultPartnerData[0];
        } else if (typeof defaultPartnerData === "object") {
            partnerId = defaultPartnerData.id;
        } else {
            partnerId = defaultPartnerData;
        }
        if (!partnerId) {
            return;
        }
        let partner = this.pos.models["res.partner"].get(partnerId);
        if (!partner) {
            const results = await this.pos.data.searchRead(
                "res.partner",
                [["id", "=", partnerId]],
            );
            partner = results && results.length > 0 ? results[0] : null;
        }
        if (partner) {
            this.currentOrder.set_partner(partner);
            console.log("[MoMo] Auto-assigned default customer:", partner.name);
        }
    },

    async sendPaymentRequest(line) {
        try {
            await super.sendPaymentRequest(line);
        } catch (error) {
            console.error("[MoMo] sendPaymentRequest error:", error);
            this.pos.paymentTerminalInProgress = false;
            this.pos.momoQrData = null;
        }
    },
});
