"""Residual plot. pyqtgraph is imported only when samples arrive."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from foamstudio.core.logparse import ResidualSample


class ResidualPlot(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("residualPlot")
        self.summary = QLabel(self.tr("No residuals yet."))
        self.summary.setWordWrap(True)
        self.summary.setObjectName("residualSummary")
        layout = QVBoxLayout(self)
        layout.addWidget(self.summary)
        self._plot: QWidget | None = None
        self._coeff_plot: QWidget | None = None
        self.coeffs = QLabel("")
        self.coeffs.setObjectName("coefficientSummary")
        layout.addWidget(self.coeffs)

    def set_coefficients(self, columns: dict[str, list[float]]) -> None:
        """Live Cd/Cl from forceCoeffs1, a convergence monitor next to the residuals."""
        time = columns.get("Time", [])
        wanted = [name for name in ("Cd", "Cl") if columns.get(name)]
        if not time or not wanted:
            return
        self.coeffs.setText(
            "  ".join(f"{name} {columns[name][-1]:.5g}" for name in wanted)
            + f"  (t = {time[-1]:g})"
        )
        try:
            import pyqtgraph as pg

            if self._coeff_plot is None:
                plot = pg.PlotWidget()
                plot.setObjectName("coefficientGraph")
                plot.addLegend()
                self.layout().addWidget(plot)
                self._coeff_plot = plot
            assert isinstance(self._coeff_plot, pg.PlotWidget)
            self._coeff_plot.clear()
            for index, name in enumerate(wanted):
                self._coeff_plot.plot(time, columns[name], name=name, pen=pg.intColor(index))
        except Exception as exc:
            self.coeffs.setText(self.coeffs.text() + f"\nThe coefficient plot failed: {exc}")

    def set_samples(self, samples: list[ResidualSample]) -> None:
        if not samples:
            self.summary.setText(self.tr("No residuals yet."))
            return
        lines = [f"{item.time:g} {item.field} {item.initial:.3g}" for item in samples[-8:]]
        self.summary.setText("\n".join(lines))
        self._try_plot(samples)

    def _try_plot(self, samples: list[ResidualSample]) -> None:
        try:
            import pyqtgraph as pg
        except Exception as exc:
            self.summary.setText(self.summary.text() + f"\n\npyqtgraph is not available: {exc}")
            return
        try:
            if self._plot is None:
                plot = pg.PlotWidget()
                plot.setObjectName("residualGraph")
                plot.addLegend()
                self.layout().addWidget(plot)
                self._plot = plot
            assert isinstance(self._plot, pg.PlotWidget)
            self._plot.clear()
            fields = sorted({item.field for item in samples})
            for field in fields:
                rows = [item for item in samples if item.field == field]
                self._plot.plot(
                    [item.time for item in rows],
                    [item.initial for item in rows],
                    name=field,
                )
        except Exception as exc:
            self.summary.setText(
                self.summary.text()
                + f"\n\nThe residual plot failed: {exc}\n\nThe numbers above are the samples."
            )
