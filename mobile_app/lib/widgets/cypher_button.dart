import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../theme/colors.dart';
import '../theme/app_theme.dart';

/// `success` exists because `controls_screen.dart` reached for a green
/// confirm button by passing a `style:` parameter this widget never had —
/// a compile error, not a styling preference. Colours belong in the
/// variant, so the design system stays the only place that knows them.
enum CypherButtonVariant { primary, secondary, ghost, danger, success }

class CypherButton extends StatefulWidget {
  final String label;
  final VoidCallback? onTap;
  final CypherButtonVariant variant;
  final Widget? icon;
  final bool loading;
  final bool fullWidth;
  final double height;

  const CypherButton({
    super.key,
    required this.label,
    this.onTap,
    this.variant  = CypherButtonVariant.primary,
    this.icon,
    this.loading  = false,
    this.fullWidth = true,
    this.height   = 44,
  });

  @override
  State<CypherButton> createState() => _CypherButtonState();
}

class _CypherButtonState extends State<CypherButton>
    with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  late Animation<double> _scale;

  @override
  void initState() {
    super.initState();
    _ctrl  = AnimationController(vsync: this, duration: const Duration(milliseconds: 100));
    _scale = Tween<double>(begin: 1, end: 0.96).animate(
      CurvedAnimation(parent: _ctrl, curve: Curves.easeOut),
    );
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  void _onTapDown(_) {
    if (widget.onTap == null || widget.loading) return;
    HapticFeedback.lightImpact();
    _ctrl.forward();
  }

  void _onTapUp(_) => _ctrl.reverse();
  void _onTapCancel() => _ctrl.reverse();

  @override
  Widget build(BuildContext context) {
    final (bg, fg, border) = switch (widget.variant) {
      CypherButtonVariant.primary   => (CypherColors.accent, Colors.white, Colors.transparent),
      CypherButtonVariant.secondary => (CypherColors.bgCard, CypherColors.textPrimary, CypherColors.border),
      CypherButtonVariant.ghost     => (Colors.transparent, CypherColors.textSecondary, Colors.transparent),
      CypherButtonVariant.danger    => (CypherColors.errorDim, CypherColors.error, CypherColors.error.withOpacity(0.3)),
      CypherButtonVariant.success   => (CypherColors.successDim, CypherColors.success, CypherColors.success.withOpacity(0.3)),
    };

    return GestureDetector(
      onTapDown: _onTapDown,
      onTapUp: _onTapUp,
      onTapCancel: _onTapCancel,
      onTap: widget.loading ? null : widget.onTap,
      child: ScaleTransition(
        scale: _scale,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 150),
          height: widget.height,
          width: widget.fullWidth ? double.infinity : null,
          padding: widget.fullWidth ? EdgeInsets.zero : const EdgeInsets.symmetric(horizontal: 20),
          decoration: BoxDecoration(
            color: widget.onTap == null ? CypherColors.bgHover : bg,
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: border, width: 1),
          ),
          child: Center(
            child: widget.loading
                ? SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: fg,
                    ),
                  )
                : Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      if (widget.icon != null) ...[
                        IconTheme(data: IconThemeData(color: fg, size: 16), child: widget.icon!),
                        const SizedBox(width: 8),
                      ],
                      Text(
                        widget.label,
                        style: AppTheme.subtitle(context).copyWith(
                          fontSize: 14,
                          fontWeight: FontWeight.w600,
                          color: widget.onTap == null ? CypherColors.textDisabled : fg,
                        ),
                      ),
                    ],
                  ),
          ),
        ),
      ),
    );
  }
}
