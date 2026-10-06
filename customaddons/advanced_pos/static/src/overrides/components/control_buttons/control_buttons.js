/** @odoo-module **/

import {_t} from "@web/core/l10n/translation";
import {ControlButtons} from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import {patch} from "@web/core/utils/patch";

patch(ControlButtons.prototype, {
    // Kế thừa lại hàm nhận quà
   async _applyReward(reward, coupon_id, potentialQty) {

        const order = this.pos.get_order();

        const existedRewardLine = order
            .get_orderlines()
            .find((line) => line.reward_id && line.reward_id.id === reward.id);

        if (existedRewardLine) {
            this.notification.add(
                _t("Reward already claimed once. You cannot claim it again.")
            );
            return false;
        }

        return await super._applyReward(reward, coupon_id, potentialQty);
    },
});