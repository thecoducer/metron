import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../services/portfolio_provider.dart';
import '../theme/app_colors.dart';
import '../utils/formatters.dart';
import '../widgets/widgets.dart';

class AssetsScreen extends StatefulWidget {
  const AssetsScreen({super.key});

  @override
  State<AssetsScreen> createState() => _AssetsScreenState();
}

class _AssetsScreenState extends State<AssetsScreen>
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
                labelStyle:
                    const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
                unselectedLabelStyle:
                    const TextStyle(fontSize: 14, fontWeight: FontWeight.w400),
                tabs: const [
                  Tab(text: 'Gold'),
                  Tab(text: 'Fixed Deposits'),
                  Tab(text: 'Provident Fund'),
                ],
              ),
            ),
            Expanded(
              child: TabBarView(
                controller: _tabController,
                children: [
                  _GoldTab(provider: provider),
                  _FixedDepositsTab(provider: provider),
                  _ProvidentFundTab(provider: provider),
                ],
              ),
            ),
          ],
        );
      },
    );
  }
}

// ── Gold Tab ──
class _GoldTab extends StatelessWidget {
  final PortfolioProvider provider;
  const _GoldTab({required this.provider});

  @override
  Widget build(BuildContext context) {
    final gold = provider.gold;
    final totalInvested = gold.fold<double>(0, (s, g) => s + g.investedValue);
    final totalCurrent = gold.fold<double>(0, (s, g) => s + g.currentValue);
    final totalWeight = gold.fold<double>(0, (s, g) => s + g.weightGrams);

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        // Overview
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: [
                const Color(0xFFFECA57).withAlpha(20),
                const Color(0xFFFECA57).withAlpha(8),
              ],
            ),
            borderRadius: BorderRadius.circular(16),
            border:
                Border.all(color: const Color(0xFFFECA57).withAlpha(60)),
          ),
          child: Column(
            children: [
              Row(
                children: [
                  const Icon(Icons.diamond_rounded,
                      color: Color(0xFFFECA57), size: 28),
                  const SizedBox(width: 12),
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'Total Gold Holdings',
                        style: TextStyle(
                            color: AppColors.textSecondary, fontSize: 12),
                      ),
                      Text(
                        '${totalWeight.toStringAsFixed(1)} grams',
                        style: const TextStyle(
                          color: AppColors.textPrimary,
                          fontSize: 22,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
              const SizedBox(height: 14),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceAround,
                children: [
                  _MiniStat(
                      label: 'Invested',
                      value: Formatters.compactCurrency(totalInvested)),
                  _MiniStat(
                      label: 'Current',
                      value: Formatters.compactCurrency(totalCurrent)),
                  _MiniStat(
                    label: 'P&L',
                    value: Formatters.compactCurrency(
                        totalCurrent - totalInvested),
                    valueColor: totalCurrent >= totalInvested
                        ? AppColors.profit
                        : AppColors.loss,
                  ),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 20),
        const SectionHeader(title: 'Holdings'),
        ...gold.map((g) => _GoldCard(gold: g)),
      ],
    );
  }
}

class _GoldCard extends StatelessWidget {
  final dynamic gold;
  const _GoldCard({required this.gold});

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
      child: Column(
        children: [
          Row(
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  color: const Color(0xFFFECA57).withAlpha(20),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Center(
                  child: Text(
                    gold.type == 'Bars'
                        ? '🪙'
                        : gold.type == 'Coins'
                            ? '🥇'
                            : '💍',
                    style: const TextStyle(fontSize: 18),
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '${gold.type} • ${gold.purity} purity',
                      style: const TextStyle(
                        color: AppColors.textPrimary,
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      '${gold.weightGrams.toStringAsFixed(1)}g • Bought ${Formatters.date(gold.date)}',
                      style: const TextStyle(
                          color: AppColors.textMuted, fontSize: 12),
                    ),
                  ],
                ),
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    Formatters.compactCurrency(gold.currentValue),
                    style: const TextStyle(
                      color: AppColors.textPrimary,
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  if (gold.type != 'Jewelry') ...[
                    const SizedBox(height: 2),
                    Text(
                      '${gold.pnl >= 0 ? "+" : ""}${Formatters.percent(gold.pnlPercentage)}',
                      style: TextStyle(
                        color: gold.pnl >= 0
                            ? AppColors.profit
                            : AppColors.loss,
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ],
              ),
            ],
          ),
          const SizedBox(height: 10),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'Buy: ₹${gold.boughtIbjaRatePerGm.toStringAsFixed(0)}/g',
                style: const TextStyle(
                    color: AppColors.textMuted, fontSize: 11),
              ),
              Text(
                'Now: ₹${gold.latestIbjaPricePerGm.toStringAsFixed(0)}/g',
                style: const TextStyle(
                    color: AppColors.textSecondary, fontSize: 11),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

// ── Fixed Deposits Tab ──
class _FixedDepositsTab extends StatelessWidget {
  final PortfolioProvider provider;
  const _FixedDepositsTab({required this.provider});

  @override
  Widget build(BuildContext context) {
    final fds = provider.fixedDeposits;
    final totalPrincipal =
        fds.fold<double>(0, (s, f) => s + f.principal);
    final totalCurrent =
        fds.fold<double>(0, (s, f) => s + f.currentValue);

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: [
                AppColors.info.withAlpha(20),
                AppColors.info.withAlpha(8),
              ],
            ),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: AppColors.info.withAlpha(60)),
          ),
          child: Row(
            children: [
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: AppColors.info.withAlpha(25),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: const Icon(Icons.account_balance_rounded,
                    color: AppColors.info, size: 22),
              ),
              const SizedBox(width: 14),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Total FD Value',
                    style: TextStyle(
                        color: AppColors.textSecondary, fontSize: 12),
                  ),
                  Text(
                    Formatters.compactCurrency(totalCurrent),
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
                  const Text('Returns',
                      style: TextStyle(
                          color: AppColors.textMuted, fontSize: 11)),
                  Text(
                    '+${Formatters.compactCurrency(totalCurrent - totalPrincipal)}',
                    style: const TextStyle(
                      color: AppColors.profit,
                      fontSize: 15,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 20),
        const SectionHeader(title: 'Your Deposits'),
        ...fds.map((f) => _FdCard(fd: f)),
      ],
    );
  }
}

class _FdCard extends StatelessWidget {
  final dynamic fd;
  const _FdCard({required this.fd});

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
      child: Column(
        children: [
          Row(
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  color: AppColors.info.withAlpha(20),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: const Center(
                  child: Text('🏦', style: TextStyle(fontSize: 18)),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      fd.bankName,
                      style: const TextStyle(
                        color: AppColors.textPrimary,
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      '${fd.interestRate}% p.a. • ${fd.depositYear}Y${fd.depositMonth > 0 ? " ${fd.depositMonth}M" : ""}',
                      style: const TextStyle(
                          color: AppColors.textMuted, fontSize: 12),
                    ),
                  ],
                ),
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    Formatters.currency(fd.currentValue),
                    style: const TextStyle(
                      color: AppColors.textPrimary,
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    '+${Formatters.compactCurrency(fd.estimatedReturns)}',
                    style: const TextStyle(
                      color: AppColors.profit,
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ],
          ),
          const SizedBox(height: 12),
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: AppColors.cardDarkElevated,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                _InfoChip(
                    label: 'Principal',
                    value: Formatters.compactCurrency(fd.principal)),
                _InfoChip(
                    label: 'Invested',
                    value: Formatters.date(fd.originalInvestmentDate)),
                _InfoChip(label: 'Maturity', value: fd.maturityDate),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ── Provident Fund Tab ──
class _ProvidentFundTab extends StatelessWidget {
  final PortfolioProvider provider;
  const _ProvidentFundTab({required this.provider});

  @override
  Widget build(BuildContext context) {
    final pfs = provider.providentFund;
    final totalBalance = pfs.fold<double>(0, (s, p) => s + p.closingBalance);
    final totalInterest =
        pfs.fold<double>(0, (s, p) => s + p.interestEarned);

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: [
                AppColors.accent.withAlpha(20),
                AppColors.accent.withAlpha(8),
              ],
            ),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: AppColors.accent.withAlpha(60)),
          ),
          child: Row(
            children: [
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: AppColors.accent.withAlpha(25),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: const Icon(Icons.savings_rounded,
                    color: AppColors.accent, size: 22),
              ),
              const SizedBox(width: 14),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Total EPF Corpus',
                    style: TextStyle(
                        color: AppColors.textSecondary, fontSize: 12),
                  ),
                  Text(
                    Formatters.compactCurrency(totalBalance),
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
                  const Text('Interest',
                      style: TextStyle(
                          color: AppColors.textMuted, fontSize: 11)),
                  Text(
                    '+${Formatters.compactCurrency(totalInterest)}',
                    style: const TextStyle(
                      color: AppColors.profit,
                      fontSize: 15,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 20),
        const SectionHeader(title: 'Employment Timeline'),
        ...pfs.map((p) => _PfCard(pf: p)),
      ],
    );
  }
}

class _PfCard extends StatelessWidget {
  final dynamic pf;
  const _PfCard({required this.pf});

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
      child: Column(
        children: [
          Row(
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  color: pf.isCurrent
                      ? AppColors.profit.withAlpha(20)
                      : AppColors.cardDarkElevated,
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Center(
                  child: Icon(
                    pf.isCurrent
                        ? Icons.work_rounded
                        : Icons.work_history_rounded,
                    color: pf.isCurrent
                        ? AppColors.profit
                        : AppColors.textMuted,
                    size: 20,
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Flexible(
                          child: Text(
                            pf.companyName,
                            style: const TextStyle(
                              color: AppColors.textPrimary,
                              fontSize: 14,
                              fontWeight: FontWeight.w600,
                            ),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                        if (pf.isCurrent) ...[
                          const SizedBox(width: 8),
                          Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 6, vertical: 2),
                            decoration: BoxDecoration(
                              color: AppColors.profit.withAlpha(25),
                              borderRadius: BorderRadius.circular(4),
                            ),
                            child: const Text(
                              'CURRENT',
                              style: TextStyle(
                                color: AppColors.profit,
                                fontSize: 9,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                          ),
                        ],
                      ],
                    ),
                    const SizedBox(height: 2),
                    Text(
                      '${Formatters.date(pf.startDate)} – ${pf.endDate != null ? Formatters.date(pf.endDate!) : "Present"} • ${pf.monthsWorked} months',
                      style: const TextStyle(
                          color: AppColors.textMuted, fontSize: 11),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: AppColors.cardDarkElevated,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                _InfoChip(
                    label: 'Monthly',
                    value: Formatters.compactCurrency(pf.monthlyContribution)),
                _InfoChip(
                    label: 'Balance',
                    value: Formatters.compactCurrency(pf.closingBalance)),
                _InfoChip(
                    label: 'Rate',
                    value: '${pf.effectiveRate}%'),
                _InfoChip(
                    label: 'Interest',
                    value: Formatters.compactCurrency(pf.interestEarned)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ── Shared ──
class _MiniStat extends StatelessWidget {
  final String label;
  final String value;
  final Color? valueColor;

  const _MiniStat(
      {required this.label, required this.value, this.valueColor});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text(label,
            style: const TextStyle(
                color: AppColors.textMuted, fontSize: 11)),
        const SizedBox(height: 2),
        Text(
          value,
          style: TextStyle(
            color: valueColor ?? AppColors.textPrimary,
            fontSize: 14,
            fontWeight: FontWeight.w700,
          ),
        ),
      ],
    );
  }
}

class _InfoChip extends StatelessWidget {
  final String label;
  final String value;
  const _InfoChip({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text(label,
            style: const TextStyle(
                color: AppColors.textMuted, fontSize: 10)),
        const SizedBox(height: 2),
        Text(
          value,
          style: const TextStyle(
            color: AppColors.textSecondary,
            fontSize: 11,
            fontWeight: FontWeight.w500,
          ),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
      ],
    );
  }
}
