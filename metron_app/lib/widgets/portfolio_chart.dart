import 'dart:math' as math;
import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import '../theme/app_colors.dart';

class PortfolioDonutChart extends StatelessWidget {
  final Map<String, double> allocation;

  const PortfolioDonutChart({super.key, required this.allocation});

  @override
  Widget build(BuildContext context) {
    final entries = allocation.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: AppColors.cardDark,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.border, width: 0.5),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Asset Allocation',
            style: TextStyle(
              color: AppColors.textPrimary,
              fontSize: 16,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 20),
          SizedBox(
            height: 180,
            child: Row(
              children: [
                Expanded(
                  child: PieChart(
                    PieChartData(
                      sectionsSpace: 2,
                      centerSpaceRadius: 40,
                      startDegreeOffset: -90,
                      sections: entries.asMap().entries.map((e) {
                        final idx = e.key;
                        final entry = e.value;
                        return PieChartSectionData(
                          color: AppColors.chartPalette[
                              idx % AppColors.chartPalette.length],
                          value: entry.value,
                          radius: 35,
                          showTitle: false,
                        );
                      }).toList(),
                    ),
                  ),
                ),
                const SizedBox(width: 24),
                Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: entries.asMap().entries.map((e) {
                    final idx = e.key;
                    final entry = e.value;
                    return Padding(
                      padding: const EdgeInsets.symmetric(vertical: 4),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Container(
                            width: 10,
                            height: 10,
                            decoration: BoxDecoration(
                              color: AppColors.chartPalette[
                                  idx % AppColors.chartPalette.length],
                              borderRadius: BorderRadius.circular(3),
                            ),
                          ),
                          const SizedBox(width: 8),
                          Text(
                            entry.key,
                            style: const TextStyle(
                              color: AppColors.textSecondary,
                              fontSize: 12,
                            ),
                          ),
                          const SizedBox(width: 8),
                          Text(
                            '${entry.value.toStringAsFixed(1)}%',
                            style: const TextStyle(
                              color: AppColors.textPrimary,
                              fontSize: 12,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ],
                      ),
                    );
                  }).toList(),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class MiniSparkline extends StatelessWidget {
  final bool isPositive;

  const MiniSparkline({super.key, required this.isPositive});

  @override
  Widget build(BuildContext context) {
    // Generate a simple mock sparkline
    final random = math.Random(isPositive ? 42 : 99);
    final spots = List.generate(12, (i) {
      final base = isPositive ? i * 0.8 : (12 - i) * 0.5;
      return FlSpot(i.toDouble(), base + random.nextDouble() * 3);
    });

    return SizedBox(
      width: 60,
      height: 28,
      child: LineChart(
        LineChartData(
          gridData: const FlGridData(show: false),
          titlesData: const FlTitlesData(show: false),
          borderData: FlBorderData(show: false),
          lineTouchData: const LineTouchData(enabled: false),
          lineBarsData: [
            LineChartBarData(
              spots: spots,
              isCurved: true,
              color: isPositive ? AppColors.profit : AppColors.loss,
              barWidth: 1.5,
              dotData: const FlDotData(show: false),
              belowBarData: BarAreaData(
                show: true,
                color: (isPositive ? AppColors.profit : AppColors.loss)
                    .withAlpha(20),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
