import 'package:flutter/material.dart';

/// A sliver that occupies a fixed amount of main-axis space.
///
/// Flutter ships [SliverToBoxAdapter] but no fixed-height sliver spacer.
/// `home_screen.dart` called `const SliverSizedBox(height: …)` in three places
/// and the class did not exist anywhere in the project — not in `lib/`, not at
/// the base commit, and not in any dependency — so the mobile app did not
/// compile. See audit F-12.
///
/// Deliberately tiny: it exists to make the call sites honest, not to become a
/// layout system. The design-system work in
/// `docs/plans/rebuild-mobile-ui.md` decides what belongs in `packages/cypher_ui`.
class SliverSizedBox extends StatelessWidget {
  /// Space to occupy along the main axis.
  final double height;

  const SliverSizedBox({super.key, this.height = 0});

  @override
  Widget build(BuildContext context) =>
      SliverToBoxAdapter(child: SizedBox(height: height));
}
