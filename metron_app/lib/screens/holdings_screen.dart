import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../services/portfolio_provider.dart';
import '../theme/app_colors.dart';
import '../utils/formatters.dart';
import '../widgets/widgets.dart';

class HoldingsScreen extends StatefulWidget {
  const HoldingsScreen({super.key});

  @override
  State<HoldingsScreen> createState() => _HoldingsScreenState();
}

class _HoldingsScreenState extends State<HoldingsScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 3, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<PortfolioProvider>(
      builder: (context, provider, _) {
        return Column(
          children: [
            // ── Tab Bar ──
            Container(
              decoration: const BoxDecoration(
                color: AppColors.surfaceDark,
                border: Border(
                    bottom: BorderSide(color: AppColors.divider, width: 0.5)),
              ),
              child: TabBar(
                controller: _tabController,
                indicatorColor: AppColors.primary,
                indicatorWeight: 2.5,
                labelColor: AppColors.primary,
                unselectedLabelColor: AppColors.textMuted,
                labelStyle: const TextStyle(
                    fontSize: 14, fontWeight: FontWeight.w600),
                unselectedLabelStyle: const TextStyle(
                    fontSize: 14, fontWeight: FontWeight.w400),
                tabs: [
                  Tab(
                      text:
                          'Stocks (${provider.stocks.length})'),
                  Tab(
                      text:
                          'Mutual Funds (${provider.mutualFunds.length})'),
                  Tab(text: 'SIPs (${provider.sips.length})'),
                ],
              ),
            ),

            // ── Tab Views ──
            Expanded(
              child: TabBarView(
                controller: _tabController,
                children: [
                  _StocksTab(provider: provider),
                  _MutualFundsTab(provider: provider),
                  _SipsTab(provider: provider),
                ],
              ),
            ),
          ],
        );
      },
    );
  }
}

// ── Stocks Tab ──
class _StocksTab extends StatelessWidget {
  final PortfolioProvider provider;
  const _StocksTab({required this.provider});

  @override
  Widget build(BuildContext context) {
    final stocks = provider.stocks;
    final totalInvested =
        stocks.fold<double>(0, (s, h) => s + h.invested);
    final totalCurrent =
        stocks.fold<double>(0, (s, h) => s + h.currentValue);
    final totalPnl = totalCurrent - totalInvested;
    final pnlPct = totalInvested > 0 ? (totalPnl / totalInvested) * 100 : 0.0;

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        // Summary row
        _AssetSummaryBanner(
          invested: totalInvested,
          current: totalCurrent,
          pnl: totalPnl,
          pnlPct: pnlPct,
        ),
        const SizedBox(height: 16),
        // Holdings list
        Container(
          decoration: BoxDecoration(
            color: AppColors.cardDark,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: AppColors.border, width: 0.5),
          ),
          child: Column(
            children: stocks.asMap().entries.map((e) {
              final s = e.value;
              final isLast = e.key == stocks.length - 1;
              return Column(
                children: [
                  HoldingListTile(
                    symbol: s.tradingSymbol,
                    subtitle:
                        '${s.quantity} qty @ ${Formatters.currency(s.averagePrice, decimals: true)}',
                    value: Formatters.currency(s.currentValue),
                    pnl:
                        '${s.pnl >= 0 ? "+" : ""}${Formatters.compactCurrency(s.pnl)} (${Formatters.percent(s.pnlPercentage)})',
                    isPositive: s.pnl >= 0,
                  ),
                  if (!isLast)
                    const Divider(height: 1, indent: 56, endIndent: 12),
                ],
              );
            }).toList(),
          ),
        ),
      ],
    );
  }
}

// ── Mutual Funds Tab ──
class _MutualFundsTab extends StatelessWidget {
  final PortfolioProvider provider;
  const _MutualFundsTab({required this.provider});

  @override
  Widget build(BuildContext context) {
    final mfs = provider.mutualFunds;
    final totalInvested = mfs.fold<double>(0, (s, m) => s + m.invested);
    final totalCurrent = mfs.fold<double>(0, (s, m) => s + m.currentValue);
    final totalPnl = totalCurrent - totalInvested;
    final pnlPct = totalInvested > 0 ? (totalPnl / totalInvested) * 100 : 0.0;

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        _AssetSummaryBanner(
          invested: totalInvested,
          current: totalCurrent,
          pnl: totalPnl,
          pnlPct: pnlPct,
        ),
        const SizedBox(height: 16),
        Container(
          decoration: BoxDecoration(
            color: AppColors.cardDark,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: AppColors.border, width: 0.5),
          ),
          child: Column(
            children: mfs.asMap().entries.map((e) {
              final m = e.value;
              final isLast = e.key == mfs.length - 1;
              return Column(
                children: [
                  HoldingListTile(
                    symbol: m.fund,
                    subtitle:
                        '${m.quantity.toStringAsFixed(2)} units • NAV ${Formatters.currency(m.lastPrice, decimals: true)}',
                    value: Formatters.currency(m.currentValue),
                    pnl:
                        '${m.pnl >= 0 ? "+" : ""}${Formatters.compactCurrency(m.pnl)} (${Formatters.percent(m.pnlPercentage)})',
                    isPositive: m.pnl >= 0,
                  ),
                  if (!isLast)
                    const Divider(height: 1, indent: 56, endIndent: 12),
                ],
              );
            }).toList(),
          ),
        ),
      ],
    );
  }
}

// ── SIPs Tab ──
class _SipsTab extends StatelessWidget {
  final PortfolioProvider provider;
  const _SipsTab({required this.provider});

  @override
  Widget build(BuildContext context) {
    final sips = provider.sips;
    final activeSips = sips.where((s) => s.isActive).toList();
    final pausedSips = sips.where((s) => !s.isActive).toList();
    final totalMonthly =
        activeSips.fold<double>(0, (s, p) => s + p.instalmentAmount);

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        // Monthly overview
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: [
                AppColors.primary.withAlpha(30),
                AppColors.accent.withAlpha(15),
              ],
            ),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: AppColors.primary.withAlpha(60)),
          ),
          child: Row(
            children: [
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: AppColors.primary.withAlpha(30),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: const Icon(Icons.autorenew_rounded,
                    color: AppColors.primary, size: 22),
              ),
              const SizedBox(width: 14),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Monthly SIP Amount',
                    style: TextStyle(
                      color: AppColors.textSecondary,
                      fontSize: 12,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    Formatters.currency(totalMonthly),
                    style: const TextStyle(
                      color: AppColors.textPrimary,
                      fontSize: 22,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ],
              ),
              const Spacer(),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    '${activeSips.length} Active',
                    style: const TextStyle(
                        color: AppColors.profit, fontSize: 13, fontWeight: FontWeight.w600),
                  ),
                  if (pausedSips.isNotEmpty) ...[
                    const SizedBox(height: 2),
                    Text(
                      '${pausedSips.length} Paused',
                      style: const TextStyle(
                          color: AppColors.warning, fontSize: 12),
                    ),
                  ],
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 20),

        if (activeSips.isNotEmpty) ...[
          const SectionHeader(title: 'Active SIPs'),
          ...activeSips.map((s) => _SipCard(sip: s)),
        ],
        if (pausedSips.isNotEmpty) ...[
          const SizedBox(height: 16),
          const SectionHeader(title: 'Paused SIPs'),
          ...pausedSips.map((s) => _SipCard(sip: s)),
        ],
      ],
    );
  }
}

class _SipCard extends StatelessWidget {
  final dynamic sip;
  const _SipCard({required this.sip});

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.cardDark,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.border, width: 0.5),
      ),
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: AppColors.cardDarkElevated,
              borderRadius: BorderRadius.circular(10),
            ),
            child: Center(
              child: Icon(
                sip.isActive
                    ? Icons.check_circle_outline_rounded
                    : Icons.pause_circle_outline_rounded,
                color: sip.isActive ? AppColors.profit : AppColors.warning,
                size: 20,
              ),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  sip.fund,
                  style: const TextStyle(
                    color: AppColors.textPrimary,
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 3),
                Text(
                  '${sip.completedInstalments} instalments done • ${sip.account}',
                  style: const TextStyle(
                      color: AppColors.textMuted, fontSize: 11),
                ),
              ],
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                Formatters.currency(sip.instalmentAmount),
                style: const TextStyle(
                  color: AppColors.textPrimary,
                  fontSize: 14,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                sip.frequency,
                style:
                    const TextStyle(color: AppColors.textMuted, fontSize: 11),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

// ── Shared Summary Banner ──
class _AssetSummaryBanner extends StatelessWidget {
  final double invested;
  final double current;
  final double pnl;
  final double pnlPct;

  const _AssetSummaryBanner({
    required this.invested,
    required this.current,
    required this.pnl,
    required this.pnlPct,
  });

  @override
  Widget build(BuildContext context) {
    final isPositive = pnl >= 0;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.cardDark,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.border, width: 0.5),
      ),
      child: Row(
        children: [
          _StatColumn(label: 'Invested', value: Formatters.compactCurrency(invested)),
          Container(
            width: 0.5,
            height: 36,
            color: AppColors.border,
            margin: const EdgeInsets.symmetric(horizontal: 16),
          ),
          _StatColumn(label: 'Current', value: Formatters.compactCurrency(current)),
          Container(
            width: 0.5,
            height: 36,
            color: AppColors.border,
            margin: const EdgeInsets.symmetric(horizontal: 16),
          ),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'P&L',
                  style: TextStyle(color: AppColors.textMuted, fontSize: 11),
                ),
                const SizedBox(height: 2),
                Text(
                  '${isPositive ? "+" : ""}${Formatters.compactCurrency(pnl)}',
                  style: TextStyle(
                    color: isPositive ? AppColors.profit : AppColors.loss,
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                Text(
                  Formatters.percent(pnlPct),
                  style: TextStyle(
                    color: isPositive ? AppColors.profit : AppColors.loss,
                    fontSize: 11,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _StatColumn extends StatelessWidget {
  final String label;
  final String value;
  const _StatColumn({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label,
            style: const TextStyle(color: AppColors.textMuted, fontSize: 11)),
        const SizedBox(height: 2),
        Text(
          value,
          style: const TextStyle(
            color: AppColors.textPrimary,
            fontSize: 16,
            fontWeight: FontWeight.w700,
          ),
        ),
      ],
    );
  }
}
