import 'package:intl/intl.dart';

class Formatters {
  static final _inrFormat = NumberFormat.currency(
    locale: 'en_IN',
    symbol: '₹',
    decimalDigits: 0,
  );

  static final _inrFormatDecimal = NumberFormat.currency(
    locale: 'en_IN',
    symbol: '₹',
    decimalDigits: 2,
  );

  static final _numberFormat = NumberFormat('#,##,###.##', 'en_IN');

  static final _percentFormat = NumberFormat('+0.00;-0.00');

  static String currency(double value, {bool decimals = false}) {
    if (decimals) return _inrFormatDecimal.format(value);
    return _inrFormat.format(value);
  }

  static String compactCurrency(double value) {
    if (value.abs() >= 10000000) {
      return '₹${(value / 10000000).toStringAsFixed(2)} Cr';
    } else if (value.abs() >= 100000) {
      return '₹${(value / 100000).toStringAsFixed(2)} L';
    } else if (value.abs() >= 1000) {
      return '₹${(value / 1000).toStringAsFixed(1)}K';
    }
    return _inrFormat.format(value);
  }

  static String number(double value) => _numberFormat.format(value);

  static String percent(double value) => '${_percentFormat.format(value)}%';

  static String date(String isoDate) {
    try {
      final d = DateTime.parse(isoDate);
      return DateFormat('dd MMM yyyy').format(d);
    } catch (_) {
      return isoDate;
    }
  }

  static String relativeTime(DateTime dt) {
    final diff = DateTime.now().difference(dt);
    if (diff.inMinutes < 1) return 'Just now';
    if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
    if (diff.inHours < 24) return '${diff.inHours}h ago';
    return DateFormat('dd MMM, h:mm a').format(dt);
  }
}
