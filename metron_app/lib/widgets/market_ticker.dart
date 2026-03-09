import 'package:flutter/material.dart';
import '../theme/app_colors.dart';

class MarketTickerBar extends StatelessWidget {
  final List<MarketTickerItem> items;

  const MarketTickerBar({super.key, required this.items});

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 52,
      decoration: const BoxDecoration(
        color: AppColors.surfaceDark,
        border: Border(bottom: BorderSide(color: AppColors.divider, width: 0.5)),
      ),
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 16),
        itemCount: items.length,
        separatorBuilder: (_, __) => const SizedBox(width: 24),
        itemBuilder: (context, index) {
          final item = items[index];
          return Center(
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  item.name,
                  style: const TextStyle(
                    color: AppColors.textMuted,
                    fontSize: 11,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                const SizedBox(width: 8),
                Text(
                  item.value,
                  style: const TextStyle(
                    color: AppColors.textPrimary,
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(width: 6),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                  decoration: BoxDecoration(
                    color: (item.isPositive ? AppColors.profit : AppColors.loss)
                        .withAlpha(25),
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Text(
                    item.change,
                    style: TextStyle(
                      color: item.isPositive ? AppColors.profit : AppColors.loss,
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}

class MarketTickerItem {
  final String name;
  final String value;
  final String change;
  final bool isPositive;

  const MarketTickerItem({
    required this.name,
    required this.value,
    required this.change,
    required this.isPositive,
  });
}
