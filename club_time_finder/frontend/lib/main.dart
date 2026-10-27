import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

const baseUrl = String.fromEnvironment('API_BASE_URL',
    defaultValue: 'http://localhost:8000');

void main() => runApp(const ClubTimeApp());

class ClubTimeApp extends StatelessWidget {
  const ClubTimeApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
      title: 'Club Time Finder',
      theme: ThemeData(colorSchemeSeed: Colors.indigo, useMaterial3: true),
      home: const LoginPage());
}

class Api {
  String? token;
  Future<bool> login(String email, String password) async {
    final r = await http.post(Uri.parse('$baseUrl/auth/token'),
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: {'username': email, 'password': password});
    if (r.statusCode != 200) return false;
    token = jsonDecode(r.body)['access_token'];
    return true;
  }

  Future<String?> register(String email, String password) async {
    final response = await http.post(Uri.parse('$baseUrl/auth/register'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'email': email, 'password': password}));
    if (response.statusCode == 201) {
      return null;
    }
    final body = jsonDecode(response.body) as Map<String, dynamic>;
    return body['detail']?.toString() ?? 'Could not create your account.';
  }

  Map<String, String> get headers =>
      {'Authorization': 'Bearer $token', 'Content-Type': 'application/json'};
  Future<Map<String, dynamic>> filters() async => jsonDecode(
      (await http.get(Uri.parse('$baseUrl/api/filters'), headers: headers))
          .body);
  Future<Map<String, dynamic>> recommend(Map<String, dynamic> body) async =>
      jsonDecode((await http.post(Uri.parse('$baseUrl/api/recommendations'),
              headers: headers, body: jsonEncode(body)))
          .body);
}

final api = Api();

class LoginPage extends StatefulWidget {
  const LoginPage({super.key});
  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final email = TextEditingController(text: 'admin@example.local'),
      password = TextEditingController(text: 'change-me-now');
  bool busy = false;
  bool creatingAccount = false;
  String? error;
  Future<void> submit() async {
    setState(() {
      busy = true;
      error = null;
    });
    if (creatingAccount) {
      final registrationError = await api.register(email.text, password.text);
      if (registrationError != null) {
        if (mounted) {
          setState(() {
            busy = false;
            error = registrationError;
          });
        }
        return;
      }
    }
    final ok = await api.login(email.text, password.text);
    if (!mounted) {
      return;
    }
    setState(() => busy = false);
    if (ok) {
      Navigator.pushReplacement(
          context, MaterialPageRoute(builder: (_) => const FinderPage()));
    } else {
      setState(() => error = 'Sign-in failed. Check the local credentials.');
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
      body: Center(
          child: SizedBox(
              width: 360,
              child: Card(
                  child: Padding(
                      padding: const EdgeInsets.all(24),
                      child: Column(
                          mainAxisSize: MainAxisSize.min,
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            Text('Club Time Finder',
                                style:
                                    Theme.of(context).textTheme.headlineSmall),
                            const SizedBox(height: 8),
                            const Text(
                                'Find class-free event windows for your target audience.'),
                            const SizedBox(height: 20),
                            TextField(
                                controller: email,
                                decoration:
                                    const InputDecoration(labelText: 'Email')),
                            TextField(
                                controller: password,
                                obscureText: true,
                                decoration: const InputDecoration(
                                    labelText: 'Password (12+ characters)')),
                            if (error != null)
                              Padding(
                                  padding: const EdgeInsets.only(top: 12),
                                  child: Text(error!,
                                      style:
                                          const TextStyle(color: Colors.red))),
                            const SizedBox(height: 16),
                            FilledButton(
                                onPressed: busy ? null : submit,
                                child: Text(busy
                                    ? 'Please wait…'
                                    : creatingAccount
                                        ? 'Create account'
                                        : 'Sign in')),
                            TextButton(
                                onPressed: busy
                                    ? null
                                    : () => setState(() =>
                                        creatingAccount = !creatingAccount),
                                child: Text(creatingAccount
                                    ? 'I already have an account'
                                    : 'Create an account'))
                          ]))))));
}

class FinderPage extends StatefulWidget {
  const FinderPage({super.key});
  @override
  State<FinderPage> createState() => _FinderPageState();
}

class _FinderPageState extends State<FinderPage> {
  Map<String, dynamic>? options, response;
  final majors = <String>{},
      colleges = <String>{},
      years = <String>{},
      days = <String>{},
      timePreferences = <String>{};
  String sourceMode = 'student_data';
  int semester = 1;
  int duration = 60;
  bool loading = true;
  @override
  void initState() {
    super.initState();
    load();
  }

  Future<void> load() async {
    final data = await api.filters();
    if (mounted) {
      setState(() {
        options = data;
        loading = false;
      });
    }
  }

  Future<void> run() async {
    setState(() => loading = true);
    final r = await api.recommend({
      'source_mode': sourceMode,
      'majors': majors.toList(),
      'colleges': colleges.toList(),
      'academic_years': years.toList(),
      'days': days.toList(),
      'time_preferences': timePreferences.toList(),
      'duration_minutes': duration,
      'semester': semester,
    });
    if (mounted) {
      setState(() {
        response = r;
        loading = false;
      });
    }
  }

  Widget chips(String label, List<dynamic> values, Set<String> selected,
          [Map<String, String>? displayLabels]) =>
      Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label, style: const TextStyle(fontWeight: FontWeight.bold)),
        Wrap(
            spacing: 6,
            children: values
                .map((v) => FilterChip(
                    label: Text(displayLabels?[v] ?? v),
                    selected: selected.contains(v),
                    onSelected: (on) => setState(
                        () => on ? selected.add(v) : selected.remove(v))))
                .toList())
      ]);
  Color heatColor(double value) =>
      Color.lerp(Colors.red.shade100, Colors.green.shade700, value / 100)!;
  Widget heatmap(List rows) {
    const orderedDays = [
      'Sunday',
      'Monday',
      'Tuesday',
      'Wednesday',
      'Thursday',
      'Friday',
      'Saturday'
    ];
    final bySlot = <String, dynamic>{
      for (final row in rows) '${row['day']}|${row['start_time']}': row
    };
    final times = rows.map((r) => r['start_time'].toString()).toSet().toList()
      ..sort();

    Widget cell(dynamic row) {
      if (row == null) {
        return Container(
            width: 96,
            height: 44,
            alignment: Alignment.center,
            margin: const EdgeInsets.all(2),
            decoration: BoxDecoration(
                color: Colors.grey.shade100,
                borderRadius: BorderRadius.circular(6)),
            child: const Text('—'));
      }
      final percent = (row['availability_percent'] as num).toDouble();
      return Tooltip(
          message:
              '${row['day']} ${row['start_time']}–${row['end_time']}: $percent% free',
          child: Container(
              width: 96,
              height: 44,
              alignment: Alignment.center,
              margin: const EdgeInsets.all(2),
              decoration: BoxDecoration(
                  color: heatColor(percent),
                  borderRadius: BorderRadius.circular(6)),
              child: Text('$percent%',
                  style: TextStyle(
                      fontWeight: FontWeight.w600,
                      color: percent > 55 ? Colors.white : Colors.black87))));
    }

    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const SizedBox(height: 28),
      Text('Availability heatmap',
          style: Theme.of(context).textTheme.titleLarge),
      const Text(
          'Times run top-to-bottom; days run Sunday through Saturday. Darker green means higher estimated availability.'),
      const SizedBox(height: 10),
      SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Column(children: [
              const SizedBox(width: 58, height: 32),
              ...times.map((time) => SizedBox(
                  width: 58,
                  height: 48,
                  child: Align(
                      alignment: Alignment.centerRight, child: Text(time))))
            ]),
            ...orderedDays.map((day) => Column(children: [
                  SizedBox(
                      width: 100,
                      height: 32,
                      child: Center(
                          child: Text(day.substring(0, 3),
                              style: const TextStyle(
                                  fontWeight: FontWeight.bold)))),
                  ...times.map((time) => cell(bySlot['$day|$time']))
                ]))
          ]))
    ]);
  }

  @override
  Widget build(BuildContext context) {
    if (loading && options == null) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    final rows = (response?['recommendations'] as List? ?? []);
    final map = (response?['heatmap'] as List? ?? []);
    return Scaffold(
        appBar: AppBar(title: const Text('Club Time Finder')),
        body: Center(
            child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 900),
                child: ListView(padding: const EdgeInsets.all(24), children: [
                  Text('Choose your audience',
                      style: Theme.of(context).textTheme.headlineSmall),
                  const SizedBox(height: 8),
                  Text(sourceMode == 'student_data'
                      ? 'Student data scales local class-free patterns to the Indianapolis planning population.'
                      : 'Class schedule data estimates conflicts from enrolled seats in sections mapped to each selected course year.'),
                  const SizedBox(height: 24),
                  Row(children: [
                    Expanded(
                        child: FilledButton(
                            onPressed: () => setState(() {
                                  sourceMode = 'student_data';
                                  response = null;
                                }),
                            style: FilledButton.styleFrom(
                                backgroundColor: sourceMode == 'student_data'
                                    ? null
                                    : Colors.grey),
                            child: const Text('From student data'))),
                    const SizedBox(width: 12),
                    Expanded(
                        child: FilledButton(
                            onPressed: () => setState(() {
                                  sourceMode = 'class_schedule_data';
                                  response = null;
                                }),
                            style: FilledButton.styleFrom(
                                backgroundColor:
                                    sourceMode == 'class_schedule_data'
                                        ? null
                                        : Colors.grey),
                            child: const Text('From class schedule data')))
                  ]),
                  const SizedBox(height: 24),
                  chips('Preferred event day(s)', options!['days'], days),
                  const SizedBox(height: 16),
                  chips('Time preference', options!['time_preferences'],
                      timePreferences, const {
                    'business_hours': 'Business hours (starts 9 AM–5 PM, M–F)',
                    'after_hours': 'After hours (starts 4 PM–9 PM, M–F)',
                  }),
                  const SizedBox(height: 16),
                  chips('Colleges', options!['colleges'], colleges),
                  const SizedBox(height: 16),
                  chips('Majors', options!['majors'], majors),
                  const SizedBox(height: 16),
                  chips(
                      sourceMode == 'student_data'
                          ? 'Academic years'
                          : 'Course year(s)',
                      options!['academic_years'],
                      years,
                      const {
                        'Freshman': '1 - Freshman',
                        'Sophomore': '2 - Sophomore',
                        'Junior': '3 - Junior',
                        'Senior': '4 - Senior',
                      }),
                  const SizedBox(height: 16),
                  Text('Semester',
                      style: const TextStyle(fontWeight: FontWeight.bold)),
                  const SizedBox(height: 6),
                  Row(children: [
                    Expanded(
                        child: FilledButton(
                            onPressed: () => setState(() {
                                  semester = 1;
                                  response = null;
                                }),
                            style: FilledButton.styleFrom(
                                backgroundColor:
                                    semester == 1 ? null : Colors.grey),
                            child: const Text('Fall (1)'))),
                    const SizedBox(width: 12),
                    Expanded(
                        child: FilledButton(
                            onPressed: () => setState(() {
                                  semester = 2;
                                  response = null;
                                }),
                            style: FilledButton.styleFrom(
                                backgroundColor:
                                    semester == 2 ? null : Colors.grey),
                            child: const Text('Spring (2)'))),
                  ]),
                  const SizedBox(height: 6),
                  Text(
                      sourceMode == 'class_schedule_data'
                          ? 'Fall uses classes marked 1–4; Spring uses classes marked 1.5–4.5.'
                          : 'Semester is used when analyzing class schedule data.',
                      style: Theme.of(context).textTheme.bodySmall),
                  const SizedBox(height: 16),
                  DropdownButtonFormField<int>(
                      initialValue: duration,
                      decoration:
                          const InputDecoration(labelText: 'Event duration'),
                      items: const [30, 60, 90, 120, 150, 180]
                          .map((m) => DropdownMenuItem(
                              value: m, child: Text('$m minutes')))
                          .toList(),
                      onChanged: (v) => setState(() => duration = v!)),
                  const SizedBox(height: 20),
                  FilledButton(
                      onPressed: loading ? null : run,
                      child: Text(loading ? 'Analyzing…' : 'Find best times')),
                  if (response != null) ...[
                    const SizedBox(height: 28),
                    Text(
                        'Best matches · ${response!['target_students']} ${response!['population_label']}',
                        style: Theme.of(context).textTheme.titleMedium),
                    const SizedBox(height: 4),
                    Text(response!['population_assumption'] ?? '',
                        style: Theme.of(context).textTheme.bodySmall),
                    const SizedBox(height: 8),
                    ...rows.map((r) => Card(
                        child: ListTile(
                            title: Text(
                                '${r['day']} · ${r['start_time']}–${r['end_time']}'),
                            subtitle: Text(
                                '${r['free_students']} estimated free · ${r['busy_students']} in class'),
                            trailing: Text('${r['availability_percent']}%',
                                style:
                                    Theme.of(context).textTheme.titleLarge)))),
                    heatmap(map)
                  ]
                ]))));
  }
}
