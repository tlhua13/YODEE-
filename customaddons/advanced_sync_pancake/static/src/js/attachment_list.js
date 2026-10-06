/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { AttachmentList } from "@mail/core/common/attachment_list";

patch(AttachmentList.prototype, {
    yodeeFileOpen(attachment) {
        // Sử dụng Microsoft Office Online Viewer
        console.log("Opening attachment with Microsoft Office Online Viewer:", attachment);
        const microsoftViewerBaseUrl = 'https://view.officeapps.live.com/op/embed.aspx';
        const fileUrl = `${window.location.origin}/ms_office/download/${attachment.id}`;
        const encodedFileUrl = encodeURIComponent(fileUrl);
        window.open(`${microsoftViewerBaseUrl}?src=${encodedFileUrl}`, "_blank");
    },
});
