import 'package:flutter/material.dart';
import '../config.dart';

class TeamLogo extends StatelessWidget {
  final String? url;
  final double size;

  const TeamLogo({super.key, this.url, this.size = 24});

  @override
  Widget build(BuildContext context) {
    if (url == null || url!.isEmpty) {
      return _fallback();
    }

    // Extrait l'ID du crest (ex: crests.football-data.org/5335.svg -> 5335)
    final match = RegExp(r'/(\d+)\.svg').firstMatch(url!);
    final id = match?.group(1);

    // Filtre les IDs suspects (equipes jeunes/reserves qui n'ont pas de logo)
    if (id != null) {
      final idNum = int.tryParse(id) ?? 0;
      // Les IDs < 100 sont des competitions, > 20000 = equipes jeunes
      if (idNum < 100 || idNum > 20000) {
        return _fallback();
      }
    }

    final proxiedUrl =
        'https://images.weserv.nl/?url=${Uri.encodeComponent(url!.replaceFirst('https://', '').replaceFirst('http://', ''))}&output=png';

    return ClipOval(
      child: Image.network(
        proxiedUrl,
        width: size,
        height: size,
        fit: BoxFit.contain,
        loadingBuilder: (context, child, progress) {
          if (progress == null) return child;
          return _fallback();
        },
        errorBuilder: (context, error, stackTrace) => _fallback(),
      ),
    );
  }

  Widget _fallback() {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: const Color(PRIMARY_COLOR).withValues(alpha: 0.1),
        shape: BoxShape.circle,
      ),
      child: Icon(
        Icons.shield,
        size: size * 0.6,
        color: const Color(PRIMARY_COLOR),
      ),
    );
  }
}
