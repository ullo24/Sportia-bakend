import 'package:flutter/material.dart';
import '../config.dart';
import 'matches_screen.dart';
import 'top_predictions_screen.dart';
import 'profile_screen.dart';
import 'admin_screen.dart';
import 'tickets_screen.dart';
import 'won_predictions_screen.dart';

class HomeScreen extends StatefulWidget {
  final bool isAdmin;
  const HomeScreen({super.key, required this.isAdmin});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _index = 0;

  @override
  Widget build(BuildContext context) {
    final pages = <Widget>[
      const MatchesScreen(),
      const TicketsScreen(),
      const TopPredictionsScreen(),
      const WonPredictionsScreen(),
      if (widget.isAdmin) const AdminScreen(),
      const ProfileScreen(),
    ];

    final destinations = <NavigationDestination>[
      const NavigationDestination(
        icon: Icon(Icons.calendar_today_outlined),
        selectedIcon: Icon(Icons.calendar_today),
        label: 'Matchs',
      ),
      const NavigationDestination(
        icon: Icon(Icons.confirmation_number_outlined),
        selectedIcon: Icon(Icons.confirmation_number),
        label: 'Tickets',
      ),
      const NavigationDestination(
        icon: Icon(Icons.insights_outlined),
        selectedIcon: Icon(Icons.insights),
        label: 'Top',
      ),
      const NavigationDestination(
        icon: Icon(Icons.emoji_events_outlined),
        selectedIcon: Icon(Icons.emoji_events),
        label: 'Réussies',
      ),
      if (widget.isAdmin)
        const NavigationDestination(
          icon: Icon(Icons.admin_panel_settings_outlined),
          selectedIcon: Icon(Icons.admin_panel_settings),
          label: 'Admin',
        ),
      const NavigationDestination(
        icon: Icon(Icons.person_outline),
        selectedIcon: Icon(Icons.person),
        label: 'Profil',
      ),
    ];

    return Scaffold(
      appBar: AppBar(
        title: Row(
          children: [
            const Icon(Icons.sports_soccer, size: 24),
            const SizedBox(width: 8),
            Text(widget.isAdmin ? 'SportIA • Admin' : 'SportIA Predict'),
          ],
        ),
        actions: [
          if (widget.isAdmin)
            Padding(
              padding: const EdgeInsets.only(right: 12),
              child: Chip(
                label: const Text(
                  'ADMIN',
                  style: TextStyle(
                    fontSize: 10,
                    fontWeight: FontWeight.bold,
                    color: Colors.white,
                  ),
                ),
                backgroundColor: const Color(ACCENT_COLOR),
                padding: EdgeInsets.zero,
                materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
              ),
            ),
        ],
      ),
      body: pages[_index],
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        backgroundColor: Colors.white,
        indicatorColor: const Color(ACCENT_COLOR).withValues(alpha: 0.2),
        destinations: destinations,
      ),
    );
  }
}
