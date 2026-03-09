import 'package:flutter/material.dart';
import '../theme/app_colors.dart';
import '../utils/formatters.dart';

class PortfolioHeader extends StatelessWidget {
  final double totalValue;
  final double totalInvested;
  final double totalPnl;
  final DateTime? lastUpdated;

  const PortfolioHeader({
    super.key,
    required this.totalValue,
    required this.totalInvested,
    required this.totalPnl,
    this.lastUpdated,
  });

  @override
  Widget build(BuildContext context) {
    final pnlPct = totalInvested > 0 ? (totalPnl / totalInvested) * 100 : 0.0;
    final isPositive = totalPnl >= 0;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            Color(0xFF1A1F35),
            AppColors.scaffoldDark,
          ],
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Text(
                'Total Portfolio',
                style: TextStyle(
                  color: AppColors.textSecondary,
                  fontSize: 14,
                  fontWeight: FontWeight.w500,
                ),
              ),
              const Spacer(),
              if (lastUpdated != null)
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 6,
                      height: 6,
                      decoration: const BoxDecoration(
                        color: AppColors.profit,
                        shape: BoxShape.circle,
                      ),
                    ),
                    const SizedBox(width: 6),
                    Text(
                      Formatters.relativeTime(lastUpdated!),
                      style: const TextStyle(
                        color: AppColors.textMuted,
                        fontSize: 11,
                      ),
                    ),
                  ],
                ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            Formatters.compactCurrency(totalValue),
            style: const TextStyle(
              color: AppColors.textPrimary,
              fontSize: 34,
              fontWeight: FontWeight.w800,
              letterSpacing: -1,
            ),
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: (isPositive ? AppColors.profit : AppColors.loss)
                      .withAlpha(25),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      isPositive
                          ? Icons.trending_up_rounded
                          : Icons.trending_down_rounded,
                      size: 16,
                      color: isPositive ? AppColors.profit : AppColors.loss,
                    ),
                    const SizedBox(width: 4),
                    Text(
                      '${isPositive ? "+" : ""}${Formatters.compactCurrency(totalPnl)}',
                      style: TextStyle(
                        color: isPositive ? AppColors.profit : AppColors.loss,
                        fontSize: 14,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(width: 4),
                    Text(
                      '(${Formatters.percent(pnlPct)})',
                      style: TextStyle(
                        color: isPositive ? AppColors.profit : AppColors.loss,
                        fontSize: 12,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              Text(
                'Invested ${Formatters.compactCurrency(totalInvested)}',
                style: const TextStyle(
                  color: AppColors.textMuted,
                  fontSize: 12,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
