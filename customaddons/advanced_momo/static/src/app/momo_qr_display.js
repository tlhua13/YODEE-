/** @odoo-module **/

import { Component, useState, onMounted, onWillUnmount } from "@odoo/owl";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";

const POLL_INTERVAL_MS = 3000;
const POLL_TIMEOUT_MS = 300000;

export class MomoQRDisplay extends Component {
    static template = "advanced_momo.MomoQRDisplay";
    static props = {};

    setup() {
        this.pos = usePos();
        const data = this.pos.momoQrData;
        const elapsed = data?.startTime ? Math.floor((Date.now() - data.startTime) / 1000) : 0;
        const remaining = Math.max(0, Math.floor(POLL_TIMEOUT_MS / 1000) - elapsed);
        this.state = useState({
            status: "waiting",
            message: _t("Waiting for customer to scan QR code..."),
            countdown: remaining,
        });
        this.pollingTimer = null;
        this.countdownTimer = null;

        onMounted(() => {
            if (remaining <= 0) {
                this.state.status = "timeout";
                this.state.message = _t("Payment timed out. Please try again.");
                setTimeout(() => {
                    if (data?.resolve) {
                        data.resolve(false);
                    }
                }, 2000);
                return;
            }
            this.startPolling();
            this.startCountdown();
        });

        onWillUnmount(() => {
            this.stopPolling();
            this.stopCountdown();
        });
    }

    get momoData() {
        return this.pos.momoQrData;
    }

    get formattedAmount() {
        return this.env.utils.formatCurrency(this.momoData?.amount || 0);
    }

    get formattedCountdown() {
        const minutes = Math.floor(this.state.countdown / 60);
        const seconds = this.state.countdown % 60;
        return `${minutes}:${seconds.toString().padStart(2, "0")}`;
    }

    startPolling() {
        this.pollingTimer = setInterval(async () => {
            const data = this.momoData;
            if (!data) {
                this.stopPolling();
                this.stopCountdown();
                return;
            }

            const startTime = data.startTime || Date.now();
            if (Date.now() - startTime > POLL_TIMEOUT_MS) {
                this.state.status = "timeout";
                this.state.message = _t("Payment timed out. Please try again.");
                this.stopPolling();
                this.stopCountdown();
                setTimeout(() => {
                    if (data.resolve) {
                        data.resolve(false);
                    }
                }, 2000);
                return;
            }

            try {
                const result = await rpc("/api/momo/check_status", {
                    transaction_id: data.transactionId,
                });

                if (result.state === "done") {
                    this.state.status = "success";
                    this.state.message = _t("Payment successful!");
                    this.stopPolling();
                    this.stopCountdown();
                    setTimeout(() => {
                        if (data.resolve) {
                            data.resolve(true);
                        }
                    }, 1500);
                } else if (result.state === "failed") {
                    this.state.status = "failed";
                    this.state.message = result.message || _t("Payment failed");
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
            if (this.state.countdown > 0) {
                this.state.countdown--;
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

    async onForceDone() {
        this.stopPolling();
        this.stopCountdown();
        const data = this.momoData;
        try {
            await rpc("/api/momo/force_done", {
                transaction_id: data.transactionId,
            });
        } catch (error) {
            console.error("MoMo force done error:", error);
        }
        this.state.status = "success";
        this.state.message = _t("Payment marked as done.");
        setTimeout(() => {
            if (data && data.resolve) {
                data.resolve(true);
            }
        }, 1000);
    }

    onRetry() {
        this.stopPolling();
        this.stopCountdown();
        const data = this.momoData;
        if (data && data.resolve) {
            data.resolve(false);
        }
        this.pos.paymentTerminalInProgress = false;
    }

    onCancel() {
        this.stopPolling();
        this.stopCountdown();
        const data = this.momoData;
        if (data && data.resolve) {
            data.resolve(false);
        }
        this.pos.paymentTerminalInProgress = false;
    }

    onPrintQR() {
        const data = this.momoData;
        if (!data || !data.transactionId) {
            return;
        }
        const url = `/report/pdf/advanced_momo.report_momo_qr/${data.transactionId}`;
        window.open(url, "_blank");
    }
}
