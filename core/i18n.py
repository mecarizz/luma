"""Small built-in translations for the desktop application's user interface."""
from __future__ import annotations

import re
from typing import Dict

from PySide6.QtWidgets import QMessageBox

SUPPORTED_LANGUAGES = ("en", "tr")

_TURKISH: Dict[str, str] = {
    "Luma Multi-Seller Manager": "Luma Çoklu Satıcı Yöneticisi",
    "Dashboard": "Genel Bakış",
    "Orders & Labels": "Siparişler ve Etiketler",
    "Seller Config": "Satıcı Ayarları",
    "Product Catalog": "Ürün Kataloğu",
    "System Logs": "Sistem Kayıtları",
    "Language": "Dil",
    "Help": "Yardım",
    "Check for Updates": "Güncellemeleri Denetle",
    "English": "English",
    "Türkçe": "Türkçe",
    "Active Sellers": "Aktif Satıcılar",
    "Orders Processed Today": "Bugün İşlenen Siparişler",
    "Failed / Retrying": "Başarısız / Yeniden Deneniyor",
    "<b>Recent Orders Across All Sellers</b>": "<b>Tüm Satıcılardaki Son Siparişler</b>",
    "Timestamp": "Zaman",
    "Seller": "Satıcı",
    "Order No.": "Sipariş No.",
    "Cargo": "Kargo",
    "Status": "Durum",
    "Add New Seller": "Yeni Satıcı Ekle",
    "Remove Selected": "Seçileni Sil",
    "Digits only": "Yalnızca rakam girin",
    "Required for a new seller; blank keeps the saved key": "Yeni satıcı için gerekli; boş bırakırsanız kayıtlı anahtar korunur",
    "Required for a new seller; blank keeps the saved secret": "Yeni satıcı için gerekli; boş bırakırsanız kayıtlı gizli anahtar korunur",
    "Enable Auto-Switch Cargo on Failure": "Kargo firmasını otomatik değiştir",
    "Enable order monitoring": "Sipariş takibini etkinleştir",
    "Print labels automatically": "Etiketleri otomatik yazdır",
    "Seller ID:": "Satıcı ID:",
    "Seller Name:": "Satıcı Adı:",
    "API Key:": "API Anahtarı:",
    "API Secret:": "API Gizli Anahtarı:",
    "Default Cargo:": "Varsayılan Kargo:",
    "Save Seller Configuration": "Satıcı Ayarlarını Kaydet",
    "Seller configuration": "Satıcı ayarları",
    "A seller with this ID already exists. Select it to edit the saved profile.": "Bu ID ile kayıtlı bir satıcı zaten var. Düzenlemek için kayıtlı profili seçin.",
    "Could not save seller:\n{error}": "Satıcı kaydedilemedi:\n{error}",
    "Seller configuration saved.": "Satıcı ayarları kaydedildi.",
    "Remove seller": "Satıcıyı sil",
    "Select a seller to remove.": "Silmek için bir satıcı seçin.",
    "Remove seller {seller_id}?": "{seller_id} numaralı satıcı silinsin mi?",
    "Could not remove seller:\n{error}": "Satıcı silinemedi:\n{error}",
    "Viewing Context:": "Görüntüleme Bağlamı:",
    "Master Catalog (Global)": "Ana Katalog (Genel)",
    "Seller 1 Overrides": "Satıcı 1 Özelleştirmeleri",
    "Seller 2 Overrides": "Satıcı 2 Özelleştirmeleri",
    "Save Changes": "Değişiklikleri Kaydet",
    "Barcode (PK)": "Barkod (PK)",
    "Display Name": "Görünen Ad",
    "Stock Code": "Stok Kodu",
    "Product Type": "Ürün Türü",
    "Outsourced": "Tedarik Edilecek",
    "Fetch Orders": "Siparişleri Getir",
    "All sellers": "Tüm satıcılar",
    "Fetch orders to choose packages for label printing.": "Etiket yazdırmak için paketleri seçmek üzere siparişleri getirin.",
    "Select": "Seç",
    "Package ID": "Paket ID",
    "Customer": "Müşteri",
    "Current Cargo": "Mevcut Kargo",
    "Print as TEX": "TEX olarak yazdır",
    "Print as DHL": "DHL olarak yazdır",
    "Select custom cargo...": "Özel kargo seçin...",
    "Print as selected cargo": "Seçilen kargoyla yazdır",
    "Fetch orders": "Siparişleri getir",
    "No seller profiles are configured.": "Satıcı profili yapılandırılmamış.",
    "Fetching packages using each seller's configured statuses and lookback...": "Her satıcının durum ve tarih aralığı ayarlarıyla paketler getiriliyor...",
    "Found {count} package(s). Select the orders to print.{failed_text}": "{count} paket bulundu. Yazdırılacak siparişleri seçin.{failed_text}",
    "{count} seller request(s) failed.": "{count} satıcı isteği başarısız oldu.",
    "Some orders could not be fetched": "Bazı siparişler getirilemedi",
    "Print labels": "Etiketleri yazdır",
    "Select at least one package first.": "Önce en az bir paket seçin.",
    "Change cargo and print labels": "Kargoyu değiştir ve etiketleri yazdır",
    "Switch the selected package(s) to {cargo} in Trendyol and print their refreshed labels?": "Seçilen paketlerin kargosu Trendyol'da {cargo} olarak değiştirilsin ve güncel etiketleri yazdırılsın mı?",
    "Preparing and printing {count} package(s) as {cargo}...": "{count} paket {cargo} olarak hazırlanıp yazdırılıyor...",
    "Printed {count} label(s).": "{count} etiket yazdırıldı.",
    "Printing finished with errors.": "Yazdırma işlemi hatalarla tamamlandı.",
    "Label printing results": "Etiket yazdırma sonuçları",
    "Label printing complete": "Etiket yazdırma tamamlandı",
    "Orders & Labels tab": "Siparişler ve Etiketler sekmesi",
    "Seller configuration error": "Satıcı ayarı hatası",
    "The seller configuration could not be loaded. Watching is disabled.\n\n{error}": "Satıcı ayarları yüklenemedi. Otomatik takip devre dışı bırakıldı.\n\n{error}",
    "Check for updates": "Güncellemeleri denetle",
    "Update installation is available in the packaged Windows application.": "Güncelleme kurulumu yalnızca Windows uygulama sürümünde kullanılabilir.",
    "Luma is up to date (v{version}).": "Luma güncel (v{version}).",
    "Luma update available": "Luma güncellemesi mevcut",
    "{title}\nVersion {version} is available (current: {current}).": "{title}\n{version} sürümü mevcut (yüklü sürüm: {current}).",
    "{notes}\n\nDownload and install this update?": "{notes}\n\nBu güncelleme indirilip kurulsun mu?",
    "Update ready": "Güncelleme hazır",
    "The update passed its SHA-256 check and is ready to install. Restart Luma now?": "Güncellemenin SHA-256 doğrulaması başarılı. Kurulum için Luma şimdi yeniden başlatılsın mı?",
    "Update downloaded": "Güncelleme indirildi",
    "The verified update is staged at:\n{path}\nRestart the app to install it later.": "Doğrulanmış güncelleme şu konumda hazır:\n{path}\nDaha sonra kurmak için uygulamayı yeniden başlatın.",
    "Update failed": "Güncelleme başarısız",
    "Could not start the updater:\n{error}": "Güncelleme aracı başlatılamadı:\n{error}",
    "Update check failed": "Güncelleme denetlenemedi",
    "Automatic update check failed": "Otomatik güncelleme denetlenemedi. Daha sonra Yardım menüsünden yeniden deneyebilirsiniz.",
    "Operation in progress": "İşlem devam ediyor",
    "The order operation is still running. Please wait for it to finish before closing Luma.": "Sipariş işlemi devam ediyor. Luma'yı kapatmadan önce işlemin bitmesini bekleyin.",
    "DHL eCommerce Marketplace": "DHL eCommerce Pazaryeri",
    "Yurtiçi Kargo": "Yurtiçi Kargo",
    "Aras Kargo": "Aras Kargo",
    "MNG Kargo": "MNG Kargo",
    "PTT Kargo": "PTT Kargo",
    "Sürat Kargo": "Sürat Kargo",
    "Sendeo": "Sendeo",
    "Horoz Lojistik": "Horoz Lojistik",
    "Ceva Lojistik": "Ceva Lojistik",
    "Trendyol Express": "Trendyol Express",
    "DHL": "DHL",
    "TEX": "TEX",
    "Unknown": "Bilinmiyor",
    "Created": "Oluşturuldu",
    "Picking": "Hazırlanıyor",
    "Invoiced": "Faturalandı",
    "Shipped": "Kargoya Verildi",
    "Delivered": "Teslim Edildi",
    "Cancelled": "İptal Edildi",
    "UnSupplied": "Tedarik Edilemedi",
    "Returned": "İade Edildi",
    "UnDelivered": "Teslim Edilemedi",
    "Awaiting": "Beklemede",
    "Verified": "Doğrulandı",
    "printed": "Yazdırıldı",
    "printed+saved": "Yazdırıldı ve kaydedildi",
    "outsourced": "Tedarik edilecek",
    "saved": "Kaydedildi",
    "switch_failed": "Kargo değiştirilemedi",
    "baseline": "Başlangıç kaydı",
    "Active": "Aktif",
    "Error": "Hata",
    "Configuration Error": "Yapılandırma Hatası",
    "Seller ID is required.": "Satıcı ID zorunludur.",
    "Trendyol API Key is required.": "Trendyol API anahtarı zorunludur.",
    "Trendyol API Secret is required.": "Trendyol API gizli anahtarı zorunludur.",
    "Vertical shift (mm) cannot be negative.": "Dikey kaydırma (mm) negatif olamaz.",
}


def tr(text: str, language: str = "en") -> str:
    """Translate a UI string, falling back to English for unknown text."""
    if language == "tr":
        translated = _TURKISH.get(text)
        if translated is not None:
            return translated
        seller_id_error = re.fullmatch(r"Seller ID '(.+)' must contain digits only\.", text)
        if seller_id_error:
            return f"Satıcı ID '{seller_id_error.group(1)}' yalnızca rakamlardan oluşmalıdır."
        return text
    return text


def ask_yes_no(parent, title: str, text: str, language: str, **values: object) -> bool:
    """Show a confirmation dialog with buttons in the selected language."""
    prompt = QMessageBox(parent)
    prompt.setIcon(QMessageBox.Question)
    prompt.setWindowTitle(tr(title, language))
    prompt.setText(tr(text, language).format(**values))
    yes_button = prompt.addButton(
        "Yes" if language == "en" else "Evet",
        QMessageBox.YesRole,
    )
    prompt.addButton(
        "No" if language == "en" else "Hayır",
        QMessageBox.NoRole,
    )
    prompt.setDefaultButton(yes_button)
    prompt.exec()
    return prompt.clickedButton() is yes_button
