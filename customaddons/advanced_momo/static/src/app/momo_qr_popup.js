/** @odoo-module **/

import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import { useState, onMounted, onWillUnmount } from "@odoo/owl";

const POLL_INTERVAL_MS = 3000;
const POLL_TIMEOUT_MS = 300000;

export class MomoQRPopup extends ConfirmationDialog {
    static template = "advanced_momo.MomoQRPopup";
    static props = {
        ...ConfirmationDialog.props,
        line: Object,
        order: Object,
        qrCodeUrl: String,
        transactionId: Number,
    };
    static defaultProps = {
        ...ConfirmationDialog.defaultProps,
        confirmLabel: _t("Confirm Payment"),
        cancelLabel: _t("Cancel Payment"),
        title: _t("MoMo Payment"),
    };

    setup() {
        super.setup();
        this.amount = this.env.utils.formatCurrency(this.props.line.amount);
        this.pollingState = useState({
            status: "waiting",
            message: _t("Waiting for customer to scan QR code..."),
            countdown: Math.floor(POLL_TIMEOUT_MS / 1000),
        });
        this.pollingTimer = null;
        this.countdownTimer = null;
        this.startTime = null;

        onMounted(() => {
            this.startPolling();
            this.startCountdown();
        });

        onWillUnmount(() => {
            this.stopPolling();
            this.stopCountdown();
        });
    }

    startPolling() {
        this.startTime = Date.now();
        this.pollingTimer = setInterval(async () => {
            if (Date.now() - this.startTime > POLL_TIMEOUT_MS) {
                this.pollingState.status = "timeout";
                this.pollingState.message = _t("Payment timed out. Please try again.");
                this.stopPolling();
                this.stopCountdown();
                return;
            }

            try {
                const result = await rpc("/api/momo/check_status", {
                    transaction_id: this.props.transactionId,
                });

                if (result.state === "done") {
                    this.pollingState.status = "success";
                    this.pollingState.message = _t("Payment successful!");
                    this.stopPolling();
                    this.stopCountdown();
                    // Auto-confirm after brief delay to show success state
                    setTimeout(() => {
                        this._confirm();
                    }, 1500);
                } else if (result.state === "failed") {
                    this.pollingState.status = "failed";
                    this.pollingState.message = result.message || _t("Payment failed");
                    this.stopPolling();
                    this.stopCountdown();
                }
            } catch (error) {
                console.error("MoMo polling error:", error);
            }
        }, POLL_INTERVAL_MS);
    }

    startCountdown() {
        this.countdownTimer = setInterval(() => {
            if (this.pollingState.countdown > 0) {
                this.pollingState.countdown--;
            }
        }, 1000);
    }

    stopPolling() {
        if (this.pollingTimer) {
            clearInterval(this.pollingTimer);
            this.pollingTimer = null;
        }
    }

    stopCountdown() {
        if (this.countdownTimer) {
            clearInterval(this.countdownTimer);
            this.countdownTimer = null;
        }
    }

    get formattedCountdown() {
        const minutes = Math.floor(this.pollingState.countdown / 60);
        const seconds = this.pollingState.countdown % 60;
        return `${minutes}:${seconds.toString().padStart(2, "0")}`;
    }
}
