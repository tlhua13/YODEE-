/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { PaymentInterface } from "@point_of_sale/app/payment/payment_interface";
import { register_payment_method } from "@point_of_sale/app/store/pos_store";
import { rpc } from "@web/core/network/rpc";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

class PaymentMomo extends PaymentInterface {
    setup(pos, payment_method_id) {
        super.setup(pos, payment_method_id);
    }

    get fast_payments() {
        return true;
    }

    async send_payment_request(uuid) {
        const line = this.pos.models["pos.payment"].find((pl) => pl.uuid === uuid);
        if (!line) {
            console.error("[MoMo] Payment line not found for uuid:", uuid);
            return false;
        }

        const order = line.pos_order_id;

        try {
            // Auto-assign default customer (Khách lẻ) if order has no customer
            if (!order.get_partner()) {
                await this._setDefaultPartner(order);
            }
            // Step 1: Create MoMo payment via backend
            const params = {
                payment_method_id: this.payment_method_id.id,
                amount: line.amount,
                order_name: order.uuid || order.name || "POS",
                session_id: this.pos.session?.id ? this.pos.session.id : false,
            };

            const result = await rpc("/api/momo/create_payment", params);

            if (!result || !result.success) {
                const errorMsg = result?.message || _t("Failed to create MoMo payment");
                console.warn("[MoMo] Payment creation failed:", errorMsg);
                this.pos.env.services.dialog.add(AlertDialog, {
                    title: _t("MoMo Payment Error"),
                    body: errorMsg,
                });
                return false;
            }

            // Step 2: Get QR code base64 image
            const transactionId = result.transaction_id;
            const qrCodeBase64 = result.qr_code_base64;

            if (!qrCodeBase64) {
                console.warn("[MoMo] No QR code image in response");
                this.pos.env.services.dialog.add(AlertDialog, {
                    title: _t("MoMo Payment Error"),
                    body: _t("No QR code received from MoMo"),
                });
                return false;
            }

            // Step 3: Show inline QR in payment-summary via reactive state
            const paymentResult = await new Promise((resolve) => {
                this.pos.momoQrData = {
                    qrCodeUrl: qrCodeBase64,
                    transactionId: transactionId,
                    amount: line.amount,
                    orderId: result.order_id,
                    resolve: resolve,
                    startTime: Date.now()
                };
            });

            // Step 4: Clean up reactive state
            this.pos.momoQrData = null;

            if (paymentResult) {
                line.transaction_id = result.order_id;
                line.card_type = "MoMo";
                return true;
            } else {
                return false;
            }
        } catch (error) {
            console.error("[MoMo] Exception:", error);
            this.pos.momoQrData = null;
            this.pos.env.services.dialog.add(AlertDialog, {
                title: _t("MoMo Payment Error"),
                body: error.message || _t("An unexpected error occurred"),
            });
            return false;
        }
    }

    async _setDefaultPartner(order) {
        const defaultPartnerData = this.payment_method_id.momo_default_partner_id;
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
            // Partner not loaded in POS yet, fetch from server
            const results = await this.pos.data.searchRead(
                "res.partner",
                [["id", "=", partnerId]],
            );
            partner = results && results.length > 0 ? results[0] : null;
        }
        if (partner) {
            order.set_partner(partner);
            console.log("[MoMo] Auto-assigned default customer:", partner.name);
        }
    }

    send_payment_cancel(order, uuid) {
        if (this.pos.momoQrData) {
            this.pos.momoQrData.resolve(false);
            this.pos.momoQrData = null;
        }
        return Promise.resolve(true);
    }

    close() {
        if (this.pos.momoQrData) {
            this.pos.momoQrData.resolve(false);
            this.pos.momoQrData = null;
        }
    }
}

register_payment_method("momo", PaymentMomo);
