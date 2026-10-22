import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../config.dart';
import 'team_logo.dart';
import 'live_score_badge.dart';

class MatchCard extends StatelessWidget {
  final dynamic match;
  final bool isPremium;
  final VoidCallback? onTap;
  final String? liveStatus;
  final int? liveHomeScore;
  final int? liveAwayScore;

  const MatchCard({
    super.key,
    required this.match,
    this.isPremium = false,
    this.onTap,
    this.liveStatus,
    this.liveHomeScore,
    this.liveAwayScore,
  });

  @override
  Widget build(BuildContext context) {
    final homeWin = (match['home_win'] ?? 0.0) as num;
    final draw = (match['draw'] ?? 0.0) as num;
    final awayWin = (match['away_win'] ?? 0.0) as num;
    final conf = (match['confidence'] ?? 0.0) as num;
    final freeAccess = (match['free_access'] ?? 0) as int;

    final maxProb = [homeWin, draw, awayWin].reduce((a, b) => a > b ? a : b);

    DateTime? kickoff;
    if (match['kickoff'] != null) {
      try {
        kickoff = DateTime.parse(match['kickoff']).toLocal();
      } catch (_) {}
    }

    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _buildHeader(kickoff, freeAccess),
              const SizedBox(height: 14),
              _buildTeams(),
              const SizedBox(height: 16),
              _build1X2(homeWin, draw, awayWin, maxProb),
              const SizedBox(height: 12),
              isPremium ? _buildPremiumMarkets() : _buildFreeMarkets(),
              const SizedBox(height: 12),
              _buildFooter(conf),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildHeader(DateTime? kickoff, int freeAccess) {
    final status = liveStatus ?? (match['status'] ?? '').toString();
    final hScore = liveHomeScore ?? match['home_goals'];
    final aScore = liveAwayScore ?? match['away_goals'];

    final isLive = status == 'IN_PLAY' || status == 'PAUSED';
    final isFinished = status == 'FINISHED';
    final ko = kickoff;
    final isMidnight = ko != null && ko.hour == 0 && ko.minute == 0;
    final timeLabel = ko == null
        ? ''
        : (isMidnight ? 'À conf.' : DateFormat('HH:mm').format(ko));

    return Row(
      children: [
        Expanded(
          child: Row(
            children: [
              Flexible(
                child: Text(
                  match['league'] ?? 'Championnat',
                  style: const TextStyle(
                    fontSize: 12,
                    color: Color(PRIMARY_COLOR),
                    fontWeight: FontWeight.w700,
                    letterSpacing: 0.3,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              if (freeAccess == 1) ...[
                const SizedBox(width: 6),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                  decoration: BoxDecoration(
                    color: const Color(ACCENT_COLOR),
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: const Text(
                    'GRATUIT',
                    style: TextStyle(
                      fontSize: 8,
                      fontWeight: FontWeight.bold,
                      color: Colors.white,
                    ),
                  ),
                ),
              ],
            ],
          ),
        ),
        const SizedBox(width: 8),
        if (isLive && hScore != null && aScore != null)
          LiveScoreBadge(
            homeScore: hScore.toString(),
            awayScore: aScore.toString(),
            minute: status == 'PAUSED' ? 'MT' : null,
          )
        else if (isFinished && hScore != null && aScore != null)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
            decoration: BoxDecoration(
              color: Colors.grey.shade200,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: Colors.grey.shade400),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 6,
                  height: 6,
                  decoration: BoxDecoration(
                    color: Colors.grey.shade600,
                    shape: BoxShape.circle,
                  ),
                ),
                const SizedBox(width: 6),
                Text(
                  '$hScore - $aScore',
                  style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w900,
                    color: Colors.black87,
                  ),
                ),
                const SizedBox(width: 6),
                Text(
                  'FIN',
                  style: TextStyle(
                    fontSize: 9,
                    fontWeight: FontWeight.bold,
                    color: Colors.grey.shade700,
                  ),
                ),
              ],
            ),
          )
        else if (kickoff != null)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
            decoration: BoxDecoration(
              color: const Color(ACCENT_COLOR).withAlpha(30),
              borderRadius: BorderRadius.circular(6),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.access_time,
                    size: 12, color: Color(PRIMARY_COLOR)),
                const SizedBox(width: 4),
                Text(
                  timeLabel,
                  style: const TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                    color: Color(PRIMARY_COLOR),
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }

  // ===== TEAMS avec logos =====
  Widget _buildTeams() {
    return Row(
      children: [
        Expanded(
          child: Row(
            children: [
              TeamLogo(url: match['home_logo'] as String?, size: 28),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  match['home'] ?? '?',
                  style: const TextStyle(
                    fontWeight: FontWeight.w700,
                    fontSize: 14,
                    color: Color(TEXT_DARK),
                  ),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
            decoration: BoxDecoration(
              color: Colors.grey.shade100,
              borderRadius: BorderRadius.circular(6),
            ),
            child: const Text(
              'VS',
              style: TextStyle(
                color: Color(PRIMARY_COLOR),
                fontWeight: FontWeight.w800,
                fontSize: 11,
              ),
            ),
          ),
        ),
        Expanded(
          child: Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              Expanded(
                child: Text(
                  match['away'] ?? '?',
                  style: const TextStyle(
                    fontWeight: FontWeight.w700,
                    fontSize: 14,
                    color: Color(TEXT_DARK),
                  ),
                  textAlign: TextAlign.right,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              const SizedBox(width: 8),
              TeamLogo(url: match['away_logo'] as String?, size: 28),
            ],
          ),
        ),
      ],
    );
  }

  Widget _build1X2(num hw, num d, num aw, num maxProb) {
    return Row(
      children: [
        Expanded(child: _probBox('1', 'Dom.', hw, hw == maxProb)),
        const SizedBox(width: 6),
        Expanded(child: _probBox('X', 'Nul', d, d == maxProb)),
        const SizedBox(width: 6),
        Expanded(child: _probBox('2', 'Ext.', aw, aw == maxProb)),
      ],
    );
  }

  Widget _probBox(String label, String sub, num prob, bool highlight) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 4),
      decoration: BoxDecoration(
        color: highlight ? const Color(PRIMARY_COLOR) : Colors.grey.shade100,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color: highlight ? const Color(PRIMARY_COLOR) : Colors.grey.shade300,
        ),
      ),
      child: Column(
        children: [
          Text(
            label,
            style: TextStyle(
              fontSize: 15,
              fontWeight: FontWeight.w800,
              color: highlight ? Colors.white : const Color(TEXT_DARK),
            ),
          ),
          Text(
            sub,
            style: TextStyle(
              fontSize: 9,
              color: highlight ? Colors.white70 : Colors.grey.shade600,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            '${(prob * 100).toStringAsFixed(0)}%',
            style: TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.w900,
              color: highlight ? Colors.white : const Color(PRIMARY_COLOR),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildFreeMarkets() {
    final over15 = (match['over_15'] ?? 0.0) as num;
    return Column(
      children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: [
                const Color(ACCENT_COLOR).withAlpha(38),
                const Color(ACCENT_COLOR).withAlpha(13),
              ],
            ),
            borderRadius: BorderRadius.circular(10),
            border: Border.all(
              color: const Color(ACCENT_COLOR).withAlpha(102),
            ),
          ),
          child: Row(
            children: [
              const Icon(Icons.trending_up,
                  size: 16, color: Color(PRIMARY_COLOR)),
              const SizedBox(width: 8),
              const Text(
                '+1.5 buts',
                style: TextStyle(
                  fontWeight: FontWeight.bold,
                  fontSize: 13,
                  color: Color(TEXT_DARK),
                ),
              ),
              const Spacer(),
              Text(
                '${(over15 * 100).toStringAsFixed(0)}%',
                style: const TextStyle(
                  fontWeight: FontWeight.w900,
                  color: Color(PRIMARY_COLOR),
                  fontSize: 16,
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 8),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          decoration: BoxDecoration(
            color: Colors.grey.shade100,
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: Colors.grey.shade300),
          ),
          child: Row(
            children: [
              Icon(Icons.lock, size: 12, color: Colors.grey.shade600),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  '+2.5 · BTTS · Handicap · 1ère MT...',
                  style: TextStyle(
                    fontSize: 11,
                    color: Colors.grey.shade700,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: Colors.amber.shade600,
                  borderRadius: BorderRadius.circular(4),
                ),
                child: const Text(
                  'PREMIUM',
                  style: TextStyle(
                    fontSize: 8,
                    fontWeight: FontWeight.bold,
                    color: Colors.white,
                    letterSpacing: 0.3,
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildPremiumMarkets() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'MARCHÉS BUTS',
          style: TextStyle(
            fontSize: 10,
            fontWeight: FontWeight.w800,
            color: Color(PRIMARY_COLOR),
            letterSpacing: 0.6,
          ),
        ),
        const SizedBox(height: 6),
        Wrap(
          spacing: 6,
          runSpacing: 6,
          children: [
            _marketPill('+1.5', match['over_15']),
            _marketPill('+2.5', match['over_25']),
            _marketPill('-3.5', match['under_35']),
            _marketPill('-4.5', match['under_45']),
            _marketPill('BTTS', match['btts_yes']),
            _marketPill('1ère MT', match['first_half_goal']),
          ],
        ),
        const SizedBox(height: 10),
        const Text(
          'HANDICAP (-1)',
          style: TextStyle(
            fontSize: 10,
            fontWeight: FontWeight.w800,
            color: Color(PRIMARY_COLOR),
            letterSpacing: 0.6,
          ),
        ),
        const SizedBox(height: 6),
        Row(
          children: [
            Expanded(
              child: _handicapPill(
                match['home'] ?? 'Dom.',
                match['handicap_home_1'],
              ),
            ),
            const SizedBox(width: 6),
            Expanded(
              child: _handicapPill(
                match['away'] ?? 'Ext.',
                match['handicap_away_1'],
              ),
            ),
          ],
        ),
      ],
    );
  }

  Widget _marketPill(String label, dynamic prob) {
    final p = (prob ?? 0.0) as num;
    final isStrong = p >= 0.65;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: isStrong ? const Color(PRIMARY_COLOR) : Colors.grey.shade100,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: isStrong ? const Color(PRIMARY_COLOR) : Colors.grey.shade300,
        ),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            label,
            style: TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w600,
              color: isStrong ? Colors.white : const Color(TEXT_DARK),
            ),
          ),
          const SizedBox(width: 6),
          Text(
            '${(p * 100).toStringAsFixed(0)}%',
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.bold,
              color: isStrong ? Colors.white : const Color(PRIMARY_COLOR),
            ),
          ),
        ],
      ),
    );
  }

  Widget _handicapPill(String label, dynamic prob) {
    final p = (prob ?? 0.0) as num;
    final isStrong = p >= 0.30;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: isStrong
            ? const Color(PRIMARY_COLOR).withAlpha(25)
            : Colors.grey.shade100,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: isStrong ? const Color(PRIMARY_COLOR) : Colors.grey.shade300,
        ),
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(
              label,
              style: const TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w600,
                color: Color(TEXT_DARK),
              ),
              overflow: TextOverflow.ellipsis,
            ),
          ),
          Text(
            '${(p * 100).toStringAsFixed(0)}%',
            style: const TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.bold,
              color: Color(PRIMARY_COLOR),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildFooter(num conf) {
    return Row(
      children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
          decoration: BoxDecoration(
            color: _confColor(conf).withAlpha(30),
            borderRadius: BorderRadius.circular(6),
            border: Border.all(color: _confColor(conf).withAlpha(76)),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.insights, size: 12, color: _confColor(conf)),
              const SizedBox(width: 4),
              Text(
                'Conf. ${(conf * 100).toStringAsFixed(0)}%',
                style: TextStyle(
                  fontSize: 11,
                  color: _confColor(conf),
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
        ),
        const Spacer(),
        _confIndicator(conf),
        const SizedBox(width: 8),
        Icon(
          Icons.chevron_right,
          color: Colors.grey.shade400,
          size: 18,
        ),
      ],
    );
  }

  Color _confColor(num conf) {
    if (conf >= 0.7) return const Color(0xFF2E7D32);
    if (conf >= 0.4) return const Color(0xFFF57C00);
    return const Color(0xFF757575);
  }

  Widget _confIndicator(num conf) {
    final active = (conf * 4).round().clamp(1, 4);
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: List.generate(4, (i) {
        return Container(
          margin: const EdgeInsets.only(left: 3),
          width: 5,
          height: 10 + i * 3,
          decoration: BoxDecoration(
            color: i < active ? _confColor(conf) : Colors.grey.shade300,
            borderRadius: BorderRadius.circular(2),
          ),
        );
      }),
    );
  }
}
