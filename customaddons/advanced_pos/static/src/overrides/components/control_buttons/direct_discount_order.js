import {_t} from "@web/core/l10n/translation";
import {NumberPopup} from "@point_of_sale/app/utils/input_popups/number_popup";
import {AlertDialog} from "@web/core/confirmation_dialog/confirmation_dialog";
import {ControlButtons} from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import {patch} from "@web/core/utils/patch";

patch(ControlButtons.prototype, {
    async clickApplyDirectDiscount() {
        this.dialog.add(NumberPopup, {
            title: _t("Giảm giá nhập trực tiếp"),
            startingValue: 0,
            getPayload: (num) => {
                const val = this.env.utils.parseValidFloat(num.toString())
                this.apply_direct_discount(val);
            },
        });
    },
    // FIXME business method in a compoenent, maybe to move in pos_store
    // Business method – apply direct discount without tax
    async apply_direct_discount(directDiscount) {
        const order = this.pos.get_order();
        if (!order) {
            return;
        }

        console.log("apply_direct_discount:", directDiscount);

        const product = this.pos.config.discount_product_id;
        if (!product) {
            this.dialog.add(AlertDialog, {
                title: _t("No discount product found"),
                body: _t(
                    "The discount product seems misconfigured. Make sure it is flagged as 'Can be Sold' and 'Available in Point of Sale'."
                ),
            });
            return;
        }

        // Remove existing discount lines
        const lines = order.get_orderlines();
        lines.filter((line) => line.get_product() === product).forEach((line) => line.delete());

        // Ensure discount is a negative amount
        const discount = -Math.abs(directDiscount);
        if (!discount) {
            return;
        }

        // Add a single discount line WITHOUT tax
        await this.pos.addLineToCurrentOrder(
            {
                product_id: product,
                price_unit: discount,
                tax_ids: [], // No tax applied
            },
            {merge: false}
        );
    }
});
