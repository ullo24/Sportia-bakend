import 'package:flutter/material.dart';
import '../config.dart';
import '../api_service.dart';

class AdminScreen extends StatefulWidget {
  const AdminScreen({super.key});

  @override
  State<AdminScreen> createState() => _AdminScreenState();
}

class _AdminScreenState extends State<AdminScreen> {
  bool _refreshing = false;
  Map<String, dynamic> _quota = {};

  @override
  void initState() {
    super.initState();
    _loadQuota();
  }

  Future<void> _loadQuota() async {
    final q = await ApiService.getQuota();
    if (!mounted) return;
    setState(() => _quota = q);
  }

  Future<void> _refresh() async {
    setState(() => _refreshing = true);
    final ok = await ApiService.refresh();
    if (!mounted) return;
    setState(() => _refreshing = false);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          ok ? 'Refresh lancé avec succès' : 'Erreur lors du refresh',
        ),
        backgroundColor: ok ? Colors.green : Colors.red,
      ),
    );
    await _loadQuota();
  }

  @override
  Widget build(BuildContext context) {
    final used = _quota['used'] ?? 0;
    final remaining = _quota['remaining_today'] ?? 0;

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        // Carte de statut
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            gradient: const LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [Color(PRIMARY_COLOR), Color(ACCENT_COLOR)],
            ),
            borderRadius: BorderRadius.circular(16),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Row(
                children: [
                  Icon(Icons.admin_panel_settings,
                      color: Colors.white, size: 28),
                  SizedBox(width: 8),
                  Text(
                    'Panneau Admin',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 18,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              Row(
                children: [
                  _statBox('Requêtes utilisées', '$used', Colors.white),
                  const SizedBox(width: 10),
                  _statBox('Restantes', '$remaining', Colors.white),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 20),

        // Actions
        _actionTile(
          icon: Icons.refresh,
          title: 'Forcer le refresh',
          subtitle: 'Relancer la récupération des matchs',
          loading: _refreshing,
          onTap: _refreshing ? null : _refresh,
        ),
        const SizedBox(height: 8),
        _actionTile(
          icon: Icons.people,
          title: 'Utilisateurs',
          subtitle: 'Gérer les comptes',
          onTap: () {},
        ),
        const SizedBox(height: 8),
        _actionTile(
          icon: Icons.bar_chart,
          title: 'Statistiques',
          subtitle: 'Taux de réussite des prédictions',
          onTap: () {},
        ),
        const SizedBox(height: 8),
        _actionTile(
          icon: Icons.settings,
          title: 'Paramètres',
          subtitle: 'Configuration de l\'application',
          onTap: () {},
        ),
      ],
    );
  }

  Widget _statBox(String label, String value, Color color) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.15),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: Colors.white.withValues(alpha: 0.3)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              label,
              style: TextStyle(
                color: color.withValues(alpha: 0.8),
                fontSize: 11,
                fontWeight: FontWeight.w500,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              value,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 22,
                fontWeight: FontWeight.bold,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _actionTile({
    required IconData icon,
    required String title,
    required String subtitle,
    VoidCallback? onTap,
    bool loading = false,
  }) {
    return Card(
      elevation: 2,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      child: ListTile(
        leading: Container(
          padding: const EdgeInsets.all(8),
          decoration: BoxDecoration(
            color: const Color(ACCENT_COLOR).withValues(alpha: 0.12),
            borderRadius: BorderRadius.circular(10),
          ),
          child: loading
              ? const SizedBox(
                  width: 24,
                  height: 24,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    color: Color(PRIMARY_COLOR),
                  ),
                )
              : Icon(icon, color: const Color(PRIMARY_COLOR), size: 24),
        ),
        title: Text(
          title,
          style: const TextStyle(
            fontWeight: FontWeight.w600,
            fontSize: 14,
            color: Color(TEXT_DARK),
          ),
        ),
        subtitle: Text(
          subtitle,
          style: TextStyle(fontSize: 11, color: Colors.grey.shade600),
        ),
        trailing: const Icon(Icons.chevron_right),
        onTap: onTap,
      ),
    );
  }
}
