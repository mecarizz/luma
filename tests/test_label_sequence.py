import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core import label_sequence
import trendyol_labels as labels
from reportlab.lib.units import mm


class TestLabelSequence(unittest.TestCase):
    def test_sequence_persists_reuses_package_numbers_and_resets_at_11pm(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(
                label_sequence,
                "get_data_path",
                side_effect=lambda name: Path(directory) / name,
            ):
                before_reset = datetime(2026, 11, 18, 22, 59, tzinfo=label_sequence.TR_TZ)
                packages = [
                    {"shipmentPackageId": 501},
                    {"shipmentPackageId": 502},
                ]
                self.assertEqual(
                    label_sequence.reserve_print_numbers(packages, before_reset),
                    {"501": 1, "502": 2},
                )
                self.assertEqual(
                    label_sequence.reserve_print_numbers(
                        [{"shipmentPackageId": 501}, {"shipmentPackageId": 503}],
                        before_reset,
                    ),
                    {"501": 1, "503": 3},
                )

                after_reset = datetime(2026, 11, 18, 23, 0, tzinfo=label_sequence.TR_TZ)
                self.assertEqual(
                    label_sequence.reserve_print_numbers(packages, after_reset),
                    {"501": 1, "502": 2},
                )

    def test_build_pdf_passes_numbers_to_each_package_only_when_provided(self):
        package = {"shipmentPackageId": 501}
        options = SimpleNamespace(w=99, h=98)
        with patch.object(labels.canvas, "Canvas") as canvas_type:
            with patch.object(labels, "draw_label") as draw_label:
                labels.build_pdf(
                    [package],
                    "unused.pdf",
                    options,
                    label_numbers={"501": 7},
                )
                self.assertEqual(draw_label.call_args.args[-1], 7)
                draw_label.reset_mock()
                labels.build_pdf([package], "unused.pdf", options)
        draw_label.assert_called_once_with(
            canvas_type.return_value,
            package,
            99 * mm,
            98 * mm,
            options,
            None,
        )

    def test_number_badge_is_kept_clear_of_barcode_even_without_shift(self):
        package = {
            "shipmentPackageId": 501,
            "cargoTrackingNumber": "123456789",
            "shipmentAddress": {"fullName": "Test"},
            "lines": [],
        }
        options = SimpleNamespace(
            shift_y=0,
            address=False,
            footer=False,
            show_seller=False,
            stamp="none",
        )
        barcode = SimpleNamespace(width=10, drawOn=Mock())
        canvas = Mock()
        with patch.object(labels.code128, "Code128", return_value=barcode):
            with patch.object(labels.pdfmetrics, "stringWidth", return_value=4):
                with patch.object(labels, "fit_font_size", return_value=10):
                    labels.draw_label(canvas, package, 99 * mm, 98 * mm, options, 1)

        badge_rect = next(
            call for call in canvas.rect.call_args_list
            if call.kwargs.get("fill") == 1
        )
        badge_bottom = badge_rect.args[1]
        barcode_top = barcode.drawOn.call_args.args[2] + 13 * mm
        self.assertGreaterEqual(badge_bottom, barcode_top + 1 * mm)

    def test_packages_without_ids_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "shipment package ID"):
            label_sequence.reserve_print_numbers([{"orderNumber": "1001"}])


if __name__ == "__main__":
    unittest.main()
