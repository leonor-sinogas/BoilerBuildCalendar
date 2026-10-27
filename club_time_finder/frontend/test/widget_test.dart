import 'package:club_time_finder/main.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('shows the app title', (tester) async {
    await tester.pumpWidget(const ClubTimeApp());
    expect(find.text('Club Time Finder'), findsOneWidget);
  });
}
