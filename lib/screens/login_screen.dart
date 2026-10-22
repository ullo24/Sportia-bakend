import '../user_service.dart';
import 'package:flutter/material.dart';
import '../config.dart';
import 'home_screen.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _email = TextEditingController();
  final _password = TextEditingController();
  String? _error;
  bool _obscurePassword = true;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  void _login() async {
    final email = _email.text.trim();
    final password = _password.text.trim();

    if (email.isEmpty || password.isEmpty) {
      setState(() => _error = 'Remplis tous les champs');
      return;
    }

    // Admin = premium automatique
    if (email == ADMIN_EMAIL && password == ADMIN_PASSWORD) {
      await UserService.setAdmin(true);
      await UserService.setPremium(true);
      if (!mounted) return;
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(
          builder: (_) => const HomeScreen(isAdmin: true),
        ),
      );
      return;
    }

    // Utilisateur normal
    if (email.contains('@') && password.length >= 3) {
      await UserService.setAdmin(false);
      await UserService.setPremium(false);
      if (!mounted) return;
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(
          builder: (_) => const HomeScreen(isAdmin: false),
        ),
      );
      return;
    }

    setState(() => _error = 'Email ou mot de passe invalide');
  }

  void _continueAsGuest() async {
    await UserService.setAdmin(false);
    await UserService.setPremium(false);
    if (!mounted) return;
    Navigator.pushReplacement(
      context,
      MaterialPageRoute(
        builder: (_) => const HomeScreen(isAdmin: false),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              Color(PRIMARY_COLOR), // bleu foncé
              Color(ACCENT_COLOR), // bleu vif
              Color(LIGHT_BLUE), // bleu pastel
            ],
          ),
        ),
        child: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: Card(
                elevation: 12,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(24),
                ),
                child: Padding(
                  padding: const EdgeInsets.all(28),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          gradient: const LinearGradient(
                            colors: [
                              Color(PRIMARY_COLOR),
                              Color(ACCENT_COLOR),
                            ],
                          ),
                          shape: BoxShape.circle,
                          boxShadow: [
                            BoxShadow(
                              color: const Color(ACCENT_COLOR)
                                  .withValues(alpha: 0.4),
                              blurRadius: 16,
                              offset: const Offset(0, 6),
                            ),
                          ],
                        ),
                        child: const Icon(
                          Icons.sports_soccer,
                          size: 56,
                          color: Colors.white,
                        ),
                      ),
                      const SizedBox(height: 20),
                      const Text(
                        'SportIA Predict',
                        style: TextStyle(
                          fontSize: 28,
                          fontWeight: FontWeight.w800,
                          color: Color(PRIMARY_COLOR),
                          letterSpacing: 0.5,
                        ),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        'Prédictions sportives par IA',
                        style: TextStyle(
                          color: Colors.grey[600],
                          fontSize: 13,
                          fontWeight: FontWeight.w500,
                          letterSpacing: 0.3,
                        ),
                      ),
                      const SizedBox(height: 28),
                      TextField(
                        controller: _email,
                        keyboardType: TextInputType.emailAddress,
                        decoration: const InputDecoration(
                          labelText: 'Email',
                          prefixIcon: Icon(
                            Icons.email_outlined,
                            color: Color(PRIMARY_COLOR),
                          ),
                        ),
                      ),
                      const SizedBox(height: 14),
                      TextField(
                        controller: _password,
                        obscureText: _obscurePassword,
                        decoration: InputDecoration(
                          labelText: 'Mot de passe',
                          prefixIcon: const Icon(
                            Icons.lock_outline,
                            color: Color(PRIMARY_COLOR),
                          ),
                          suffixIcon: IconButton(
                            icon: Icon(
                              _obscurePassword
                                  ? Icons.visibility_off
                                  : Icons.visibility,
                              color: Colors.grey[600],
                            ),
                            onPressed: () {
                              setState(() {
                                _obscurePassword = !_obscurePassword;
                              });
                            },
                          ),
                        ),
                      ),
                      if (_error != null) ...[
                        const SizedBox(height: 12),
                        Text(
                          _error!,
                          style: const TextStyle(
                            color: Colors.red,
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ],
                      const SizedBox(height: 22),
                      SizedBox(
                        width: double.infinity,
                        height: 52,
                        child: ElevatedButton(
                          onPressed: _login,
                          child: const Text(
                            'Se connecter',
                            style: TextStyle(
                              fontSize: 16,
                              fontWeight: FontWeight.bold,
                              letterSpacing: 0.5,
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(height: 12),
                      TextButton(
                        onPressed: _continueAsGuest,
                        child: const Text('Continuer sans compte'),
                      ),
                      const SizedBox(height: 12),
                      Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color:
                              const Color(LIGHT_BLUE).withValues(alpha: 0.15),
                          borderRadius: BorderRadius.circular(10),
                          border: Border.all(
                            color:
                                const Color(LIGHT_BLUE).withValues(alpha: 0.4),
                          ),
                        ),
                        child: Column(
                          children: [
                            Text(
                              'Compte super admin :',
                              style: TextStyle(
                                fontSize: 11,
                                color: const Color(PRIMARY_COLOR),
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              'admin@sportia.com / admin123',
                              style: TextStyle(
                                fontSize: 11,
                                color: const Color(PRIMARY_COLOR)
                                    .withValues(alpha: 0.8),
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
