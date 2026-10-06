import base64
import traceback
from io import BytesIO
from itertools import product
from os import unlink

from odoo import fields, models, _
from odoo.exceptions import ValidationError, UserError
from openpyxl import load_workbook
import gc



class ImportProductUom(models.TransientModel):
    _name = 'import.product.uom'

    file = fields.Binary(string="File Excel (xlsx)", help='Upload the file here', attachment=False)
    file_name = fields.Char()

    def import_file_ver(self):
        if not self.file or not self.file_name:
            raise UserError(_("Vui lòng chọn file Excel"))

        if not (self.file_name.endswith('.xlsx') or self.file_name.endswith('.xls')):
            raise UserError(_("File Import chỉ nhận định dạng file excel .xls hoặc .xlsx"))

        excel_data = BytesIO(base64.b64decode(self.file))
        workbook = load_workbook(filename=excel_data, data_only=True)
        sheet = workbook[workbook.sheetnames[0]]

        header = [cell.value for cell in sheet[1]]
        column_map = {col: idx for idx, col in enumerate(header)}

        if 'Tham chiếu nội bộ' not in column_map or 'Đơn vị tính' not in column_map:
            raise UserError(_("File Excel phải có cột 'Mã sản phẩm' và 'Đơn vị'"))

        Product = self.env['product.template']
        Uom = self.env['uom.uom']

        error_lines = []
        row_index = 1

        for row in sheet.iter_rows(min_row=2, values_only=True):
            row_index += 1

            default_code = row[column_map['Tham chiếu nội bộ']]
            uom_name = row[column_map['Đơn vị tính']]

            if not default_code or not uom_name:
                continue

            product = Product.search([('default_code', '=', str(default_code))], limit=1)
            if not product:
                error_lines.append(f"Dòng {row_index}: Không tìm thấy SP [{default_code}]")
                continue

            uom = Uom.search([('name', '=', str(uom_name))], limit=1)
            if not uom:
                error_lines.append(f"Dòng {row_index}: Không tìm thấy ĐVT [{uom_name}]")
                continue

            if product.uom_id.category_id != uom.category_id:
                error_lines.append(
                    f"Dòng {row_index}: ĐVT [{uom_name}] khác nhóm với ĐVT hiện tại của SP [{default_code}]"
                )
                continue

            wizard = self.env['product.change.uom'].with_context(
                active_id=product.id
            ).create({
                'uom_id': uom.id,
                'uom_po_id': uom.id,
            })
            wizard.do_change()

        if error_lines:
            raise UserError(_("Import xong nhưng có lỗi:\n") + "\n".join(error_lines))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Thành công'),
                'message': _('Import & cập nhật đơn vị tính hoàn tất'),
                'type': 'success',
            }
        }