from PyQt6.QtCore import QPropertyAnimation, QPoint, QEasingCurve, QParallelAnimationGroup

class AnimationHandler:
    def __init__(self, app_instance):
        self.app_instance = app_instance

    def animate_transition(self, active_widget, incoming_widget, viewport_height):
        active_widget.show()
        incoming_widget.show()
        self.anim_out = QPropertyAnimation(active_widget, b"pos")
        self.anim_out.setDuration(1800)
        self.anim_out.setStartValue(QPoint(0, 0))
        self.anim_out.setEndValue(QPoint(0, viewport_height))
        self.anim_out.setEasingCurve(QEasingCurve.Type.InOutCubic)

        self.anim_in = QPropertyAnimation(incoming_widget, b"pos")
        self.anim_in.setDuration(1800)
        self.anim_in.setStartValue(QPoint(0, -viewport_height))
        self.anim_in.setEndValue(QPoint(0, 0))
        self.anim_in.setEasingCurve(QEasingCurve.Type.InOutCubic)

        self.group = QParallelAnimationGroup()
        self.group.addAnimation(self.anim_out)
        self.group.addAnimation(self.anim_in)
        # Geçiş bitince eski blok tamamen gizlenir: alt kenarda 1 px'lik şerit kalmaz.
        self.group.finished.connect(active_widget.hide)
        self.group.start()
        return self.group
