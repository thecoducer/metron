import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../services/portfolio_provider.dart';
import '../theme/app_colors.dart';
import '../utils/formatters.dart';
import '../widgets/widgets.dart';

class DashboardScreen extends StatelessWidget {
  final void Function(int) onNavigate;

  const DashboardScreen({super.key, required this.onNavigate});

  @override
  Widget build(BuildContext context) {
    return Consumer<PortfolioProvider>(
      builder: (context, provider, _) {
        if (provider.isLoading) {
          return const Center(
            child: CircularProgressIndicator(color: AppColors.primary),
          );
        }

        final summary = provider.summary;
        final indices = provider.marketIndices;
        final stocks = provider.stocks;
        final mfs = provider.mutualFunds;

        return RefreshIndicator(
          onRefresh: provider.refresh,
          color: AppColors.primary,
          backgroundColor: AppColors.surfaceDark,
          child: CustomScrollView(
            slivers: [
              // ── Market Ticker ──
              SliverToBoxAdapter(
                child: MarketTickerBar(
                  items: indices
                      .map((i) => MarketTickerItem(
                            name: i.name,
                            value: i.value >= 1000
                                ? Formatters.number(i.value)
                                : i.value.toStringAsFixed(2),
                            change: Formatters.percent(i.changePercentage),
                            isPositive: i.isPositive,
                          ))
                      .toList(),
                ),
              ),

              // ── Portfolio Header ──
              SliverToBoxAdapter(
                child: PortfolioHeader(
                  totalValue: summary['totalCurrent'] ?? 0,
                  totalInvested: summary['totalInvested'] ?? 0,
                  totalPnl: summary['totalPnl'] ?? 0,
                  lastUpdated: provider.lastUpdated,
                ),
              ),

              // ── Summary Cards Grid ──
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                sliver: SliverGrid.count(
                  crossAxisCount:
                      MediaQuery.sizeOf(context).width > 600 ? 3 : 2,
                  crossAxisSpacing: 12,
                  mainAxisSpacing: 12,
                  childAspectRatio: 1.35,
                  children: [
                    SummaryCard(
                      title: 'Stocks',
                      value: Formatters.compactCurrency(
                          summary['stocksCurrent'] ?? 0),
                      subtitle: _pnlText(summary['stocksCurrent'] ?? 0,
                          summary['stocksInvested'] ?? 0),
                      icon: Icons.candlestick_chart_rounded,
                      iconColor: AppColors.chartPalette[0],
                      onTap: () => onNavigate(1),
                    ),
                    SummaryCard(
                      title: 'Mutual Funds',
                      value:
                          Formatters.compactCurrency(summary['mfCurrent'] ?? 0),
                      subtitle: _pnlText(summary['mfCurrent'] ?? 0,
                          summary['mfInvested'] ?? 0),
                      icon: Icons.pie_chart_rounded,
                      iconColor: AppColors.chartPalette[1],
                      onTap: () => onNavigate(1),
                    ),
                    SummaryCard(
                      title: 'Gold',
                      value: Formatters.compactCurrency(
                          summary['goldCurrent'] ?? 0),
                      subtitle: _pnlText(summary['goldCurrent'] ?? 0,
                          summary['goldInvested'] ?? 0),
                      icon: Icons.diamond_rounded,
                      iconColor: const Color(0xFFFECA57),
                      onTap: () => onNavigate(2),
                    ),
                    SummaryCard(
                      title: 'Fixed Deposits',
                      value:
                          Formatters.compactCurrency(summary['fdCurrent'] ?? 0),
                      subtitle: _pnlText(summary['fdCurrent'] ?? 0,
                          summary['fdInvested'] ?? 0),
                      icon: Icons.account_balance_rounded,
                      iconColor: AppColors.chartPalette[4],
                      onTap: () => onNavigate(2),
                    ),
                    SummaryCard(
                      title: 'Provident Fund',
                      value:
                          Formatters.compactCurrency(summary['pfBalance'] ?? 0),
                      subtitle: _pnlText(summary['pfBalance'] ?? 0,
                          summary['pfContribution'] ?? 0),
                      icon: Icons.savings_rounded,
                      iconColor: AppColors.chartPalette[2],
                      onTap: () => onNavigate(2),
                    ),
                    SummaryCard(
                      title: 'Monthly SIPs',
                      value: Formatters.compactCurrency(
                          summary['sipMonthly'] ?? 0),
                      subtitle:
                          '${provider.sips.where((s) => s.isActive).length} active',
                      icon: Icons.autorenew_rounded,
                      iconColor: AppColors.chartPalette[5],
                      onTap: () => onNavigate(1),
                    ),
                  ],
                ),
              ),

              // ── Asset Allocation Chart ──
              if (provider.assetAllocation.isNotEmpty)
                SliverPadding(
                  padding: const EdgeInsets.fromLTRB(16, 20, 16, 0),
                  sliver: SliverToBoxAdapter(
                    child: PortfolioDonutChart(
                        allocation: provider.assetAllocation),
                  ),
                ),

              // ── Top Holdings ──
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(16, 24, 16, 0),
                sliver: SliverToBoxAdapter(
                  child: SectionHeader(
                    title: 'Top Holdings',
                    trailing: 'View All',
                    onTap: () => onNavigate(1),
                  ),
                ),
              ),
              SliverPadding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                sliver: SliverToBoxAdapter(
                  child: Container(
                    decoration: BoxDecoration(
                      color: AppColors.cardDark,
                      borderRadius: BorderRadius.circular(16),
                      border:
                          Border.all(color: AppColors.border, width: 0.5),
                    ),
                    child: Column(
                      children: [
                        ...stocks.take(5).map((s) => Column(
                              children: [
                                HoldingListTile(
                                  symbol: s.tradingSymbol,
                                  subtitle:
                                      '${s.quantity} qty • ${s.account}',
                                  value: Formatters.compactCurrency(
                                      s.currentValue),
                                  pnl: Formatters.percent(s.pnlPercentage),
                                  isPositive: s.pnl >= 0,
                                ),
                                if (s != stocks.take(5).last)
                                  const Divider(
                                      height: 1, indent: 56, endIndent: 12),
                              ],
                            )),
                      ],
                    ),
                  ),
                ),
              ),

              // ── Top Mutual Funds ──
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(16, 24, 16, 0),
                sliver: SliverToBoxAdapter(
                  child: SectionHeader(
                    title: 'Mutual Funds',
                    trailing: 'View All',
                    onTap: () => onNavigate(1),
                  ),
                ),
              ),
              SliverPadding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                sliver: SliverToBoxAdapter(
                  child: Container(
                    decoration: BoxDecoration(
                      color: AppColors.cardDark,
                      borderRadius: BorderRadius.circular(16),
                      border:
                          Border.all(color: AppColors.border, width: 0.5),
                    ),
                    child: Column(
                      children: [
                        ...mfs.take(4).map((m) => Column(
                              children: [
                                HoldingListTile(
                                  symbol: m.fund,
                                  subtitle:
                                      '${m.quantity.toStringAsFixed(2)} units',
                                  value: Formatters.compactCurrency(
                                      m.currentValue),
                                  pnl: Formatters.percent(m.pnlPercentage),
                                  isPositive: m.pnl >= 0,
                                ),
                                if (m != mfs.take(4).last)
                                  const Divider(
                                      height: 1, indent: 56, endIndent: 12),
                              ],
                            )),
                      ],
                    ),
                  ),
                ),
              ),

              const SliverPadding(padding: EdgeInsets.only(bottom: 24)),
            ],
          ),
        );
      },
    );
  }

  String _pnlText(double current, double invested) {
    final pnl = current - invested;
    final pct = invested > 0 ? (pnl / invested) * 100 : 0.0;
    final sign = pnl >= 0 ? '+' : '';
    return '$sign${Formatters.compactCurrency(pnl)} (${Formatters.percent(pct)})';
  }
}
