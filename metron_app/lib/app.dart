import 'package:flutter/material.dart';
import 'theme/app_colors.dart';
import 'screens/dashboard_screen.dart';
import 'screens/holdings_screen.dart';
import 'screens/assets_screen.dart';
import 'screens/settings_screen.dart';

class MetronApp extends StatelessWidget {
  const MetronApp({super.key});

  @override
  Widget build(BuildContext context) {
    return const AppShell();
  }
}

class AppShell extends StatefulWidget {
  const AppShell({super.key});

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  int _currentIndex = 0;

  void _onNavigate(int index) {
    setState(() => _currentIndex = index);
  }

  @override
  Widget build(BuildContext context) {
    final isWide = MediaQuery.sizeOf(context).width > 800;

    return Scaffold(
      body: SafeArea(
        child: isWide
            ? Row(
                children: [
                  _buildSideNav(),
                  const VerticalDivider(width: 1, color: AppColors.divider),
                  Expanded(child: _buildBody()),
                ],
              )
            : _buildBody(),
      ),
      bottomNavigationBar: isWide ? null : _buildBottomNav(),
    );
  }

  Widget _buildBody() {
    return IndexedStack(
      index: _currentIndex,
      children: [
        DashboardScreen(onNavigate: _onNavigate),
        const HoldingsScreen(),
        const AssetsScreen(),
        const SettingsScreen(),
      ],
    );
  }

  Widget _buildBottomNav() {
    return Container(
      decoration: const BoxDecoration(
        border: Border(top: BorderSide(color: AppColors.divider, width: 0.5)),
      ),
      child: NavigationBar(
        selectedIndex: _currentIndex,
        onDestinationSelected: _onNavigate,
        height: 65,
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.dashboard_outlined),
            selectedIcon: Icon(Icons.dashboard_rounded),
            label: 'Dashboard',
          ),
          NavigationDestination(
            icon: Icon(Icons.candlestick_chart_outlined),
            selectedIcon: Icon(Icons.candlestick_chart_rounded),
            label: 'Holdings',
          ),
          NavigationDestination(
            icon: Icon(Icons.account_balance_outlined),
            selectedIcon: Icon(Icons.account_balance_rounded),
            label: 'Assets',
          ),
          NavigationDestination(
            icon: Icon(Icons.settings_outlined),
            selectedIcon: Icon(Icons.settings_rounded),
            label: 'Settings',
          ),
        ],
      ),
    );
  }

  Widget _buildSideNav() {
    return NavigationRail(
      selectedIndex: _currentIndex,
      onDestinationSelected: _onNavigate,
      backgroundColor: AppColors.surfaceDark,
      indicatorColor: AppColors.primary.withAlpha(40),
      labelType: NavigationRailLabelType.all,
      leading: Padding(
        padding: const EdgeInsets.symmetric(vertical: 12),
        child: Container(
          width: 42,
          height: 42,
          decoration: BoxDecoration(
            gradient: const LinearGradient(
              colors: [AppColors.primary, AppColors.accent],
            ),
            borderRadius: BorderRadius.circular(12),
          ),
          child: const Center(
            child: Text(
              'M',
              style: TextStyle(
                color: Colors.white,
                fontSize: 20,
                fontWeight: FontWeight.w800,
              ),
            ),
          ),
        ),
      ),
      destinations: const [
        NavigationRailDestination(
          icon: Icon(Icons.dashboard_outlined),
          selectedIcon: Icon(Icons.dashboard_rounded),
          label: Text('Dashboard'),
        ),
        NavigationRailDestination(
          icon: Icon(Icons.candlestick_chart_outlined),
          selectedIcon: Icon(Icons.candlestick_chart_rounded),
          label: Text('Holdings'),
        ),
        NavigationRailDestination(
          icon: Icon(Icons.account_balance_outlined),
          selectedIcon: Icon(Icons.account_balance_rounded),
          label: Text('Assets'),
        ),
        NavigationRailDestination(
          icon: Icon(Icons.settings_outlined),
          selectedIcon: Icon(Icons.settings_rounded),
          label: Text('Settings'),
        ),
      ],
    );
  }
}
