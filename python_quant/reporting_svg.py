from __future__ import annotations


def build_line_chart_svg(
    *,
    title: str,
    series: list[tuple[str, list[tuple[str, float]], str]],
    y_axis_label: str,
) -> str:
    width = 960
    height = 540
    margin_left = 80
    margin_right = 40
    margin_top = 60
    margin_bottom = 80

    non_empty_series = [item for item in series if item[1]]
    if not non_empty_series:
        return empty_chart_svg(title, width, height)

    all_values = [value for _, points, _ in non_empty_series for _, value in points]
    min_value = min(all_values)
    max_value = max(all_values)
    if min_value == max_value:
        min_value *= 0.99
        max_value *= 1.01

    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom

    def x_position(index: int, total: int) -> float:
        if total <= 1:
            return margin_left + plot_width / 2
        return margin_left + plot_width * index / (total - 1)

    def y_position(value: float) -> float:
        scale = (value - min_value) / (max_value - min_value)
        return margin_top + plot_height * (1 - scale)

    grid_lines = []
    labels = []
    for step in range(5):
        ratio = step / 4
        y = margin_top + plot_height * ratio
        value = max_value - (max_value - min_value) * ratio
        grid_lines.append(
            f'<line x1="{margin_left}" y1="{y:.1f}" x2="{width - margin_right}" y2="{y:.1f}" stroke="#d0d7de" stroke-width="1" />'
        )
        labels.append(
            f'<text x="{margin_left - 10}" y="{y + 4:.1f}" font-size="12" text-anchor="end" fill="#495057">{value:.2f}</text>'
        )

    line_paths: list[str] = []
    legend_items: list[str] = []
    for index, (label, points, color) in enumerate(non_empty_series):
        commands = []
        for point_index, (_, value) in enumerate(points):
            x = x_position(point_index, len(points))
            y = y_position(value)
            prefix = "M" if point_index == 0 else "L"
            commands.append(f"{prefix} {x:.1f} {y:.1f}")
        line_paths.append(
            f'<path d="{" ".join(commands)}" fill="none" stroke="{color}" stroke-width="3" />'
        )
        legend_y = margin_top - 18 + index * 18
        legend_items.append(
            f'<rect x="{width - 180}" y="{legend_y - 10}" width="12" height="12" fill="{color}" />'
            f'<text x="{width - 160}" y="{legend_y}" font-size="12" fill="#212529">{label}</text>'
        )

    first_series_points = non_empty_series[0][1]
    x_labels = []
    label_indexes = sorted({0, len(first_series_points) // 2, len(first_series_points) - 1})
    for label_index in label_indexes:
        x = x_position(label_index, len(first_series_points))
        label = first_series_points[label_index][0]
        x_labels.append(
            f'<text x="{x:.1f}" y="{height - margin_bottom + 24}" font-size="12" text-anchor="middle" fill="#495057">{label}</text>'
        )

    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            '<rect width="100%" height="100%" fill="#ffffff" />',
            f'<text x="{margin_left}" y="30" font-size="24" font-weight="bold" fill="#212529">{title}</text>',
            *grid_lines,
            f'<line x1="{margin_left}" y1="{height - margin_bottom}" x2="{width - margin_right}" y2="{height - margin_bottom}" stroke="#495057" stroke-width="1.5" />',
            f'<line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{height - margin_bottom}" stroke="#495057" stroke-width="1.5" />',
            *labels,
            *line_paths,
            *legend_items,
            *x_labels,
            f'<text x="24" y="{margin_top + plot_height / 2:.1f}" font-size="12" fill="#495057" transform="rotate(-90 24 {margin_top + plot_height / 2:.1f})">{y_axis_label}</text>',
            "</svg>",
        ]
    )


def build_bar_chart_svg(
    *,
    title: str,
    points: list[tuple[str, float]],
    bar_color: str,
    y_axis_label: str,
) -> str:
    width = 960
    height = 540
    margin_left = 80
    margin_right = 40
    margin_top = 60
    margin_bottom = 100
    if not points:
        return empty_chart_svg(title, width, height)

    values = [value for _, value in points]
    max_value = max(max(values), 0.0)
    min_value = min(min(values), 0.0)
    if min_value == max_value:
        max_value = max_value + 1.0
        min_value = min_value - 1.0

    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom
    zero_y = margin_top + plot_height * (max_value / (max_value - min_value))

    def y_position(value: float) -> float:
        scale = (value - min_value) / (max_value - min_value)
        return margin_top + plot_height * (1 - scale)

    bar_width = plot_width / max(len(points), 1) * 0.65
    gap = plot_width / max(len(points), 1)

    grid_lines = []
    labels = []
    for step in range(5):
        ratio = step / 4
        y = margin_top + plot_height * ratio
        value = max_value - (max_value - min_value) * ratio
        grid_lines.append(
            f'<line x1="{margin_left}" y1="{y:.1f}" x2="{width - margin_right}" y2="{y:.1f}" stroke="#d0d7de" stroke-width="1" />'
        )
        labels.append(
            f'<text x="{margin_left - 10}" y="{y + 4:.1f}" font-size="12" text-anchor="end" fill="#495057">{value:.2f}</text>'
        )

    bars = []
    x_labels = []
    for index, (label, value) in enumerate(points):
        x = margin_left + index * gap + (gap - bar_width) / 2
        y = y_position(max(value, 0.0))
        bar_base = y_position(min(value, 0.0))
        bar_height = abs(bar_base - y)
        bars.append(
            f'<rect x="{x:.1f}" y="{min(y, bar_base):.1f}" width="{bar_width:.1f}" height="{bar_height:.1f}" fill="{bar_color}" rx="4" />'
        )
        x_labels.append(
            f'<text x="{x + bar_width / 2:.1f}" y="{height - margin_bottom + 24}" font-size="12" text-anchor="middle" fill="#495057">{label}</text>'
        )

    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            '<rect width="100%" height="100%" fill="#ffffff" />',
            f'<text x="{margin_left}" y="30" font-size="24" font-weight="bold" fill="#212529">{title}</text>',
            *grid_lines,
            f'<line x1="{margin_left}" y1="{zero_y:.1f}" x2="{width - margin_right}" y2="{zero_y:.1f}" stroke="#495057" stroke-width="1.5" />',
            f'<line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{height - margin_bottom}" stroke="#495057" stroke-width="1.5" />',
            *labels,
            *bars,
            *x_labels,
            f'<text x="24" y="{margin_top + plot_height / 2:.1f}" font-size="12" fill="#495057" transform="rotate(-90 24 {margin_top + plot_height / 2:.1f})">{y_axis_label}</text>',
            "</svg>",
        ]
    )


def empty_chart_svg(title: str, width: int, height: int) -> str:
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            '<rect width="100%" height="100%" fill="#ffffff" />',
            f'<text x="40" y="40" font-size="24" font-weight="bold" fill="#212529">{title}</text>',
            '<text x="40" y="90" font-size="16" fill="#6c757d">暂无可展示数据</text>',
            "</svg>",
        ]
    )


def build_heatmap_svg(
    *,
    title: str,
    x_label: str,
    y_label: str,
    points: list[tuple[str, str, float]],
) -> str:
    width = 960
    height = 540
    margin_left = 120
    margin_right = 120
    margin_top = 60
    margin_bottom = 100
    if not points:
        return empty_chart_svg(title, width, height)

    x_values = sorted({x for x, _, _ in points})
    y_values = sorted({y for _, y, _ in points})
    value_map = {(x, y): value for x, y, value in points}
    all_values = list(value_map.values())
    min_value = min(all_values)
    max_value = max(all_values)
    if min_value == max_value:
        min_value -= 1.0
        max_value += 1.0

    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom
    cell_width = plot_width / max(len(x_values), 1)
    cell_height = plot_height / max(len(y_values), 1)

    cells: list[str] = []
    x_labels: list[str] = []
    y_labels: list[str] = []

    for x_index, x_value in enumerate(x_values):
        x = margin_left + x_index * cell_width
        x_labels.append(
            f'<text x="{x + cell_width / 2:.1f}" y="{height - margin_bottom + 24}" font-size="12" text-anchor="middle" fill="#495057">{x_value}</text>'
        )

    for y_index, y_value in enumerate(y_values):
        y = margin_top + y_index * cell_height
        y_labels.append(
            f'<text x="{margin_left - 10}" y="{y + cell_height / 2 + 4:.1f}" font-size="12" text-anchor="end" fill="#495057">{y_value}</text>'
        )
        for x_index, x_value in enumerate(x_values):
            x = margin_left + x_index * cell_width
            value = value_map.get((x_value, y_value))
            if value is None:
                fill = "#f1f3f5"
                label = ""
            else:
                fill = _heatmap_color(value, min_value, max_value)
                label = f"{value:.2f}"
            cells.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell_width:.1f}" height="{cell_height:.1f}" fill="{fill}" stroke="#ffffff" stroke-width="2" />'
            )
            if label:
                cells.append(
                    f'<text x="{x + cell_width / 2:.1f}" y="{y + cell_height / 2 + 4:.1f}" font-size="12" text-anchor="middle" fill="#212529">{label}</text>'
                )

    legend_x = width - margin_right + 20
    legend_items = []
    for index in range(5):
        ratio = index / 4
        value = min_value + (max_value - min_value) * ratio
        y = margin_top + plot_height - (plot_height * ratio)
        legend_items.append(
            f'<rect x="{legend_x}" y="{y - 10:.1f}" width="20" height="20" fill="{_heatmap_color(value, min_value, max_value)}" />'
        )
        legend_items.append(
            f'<text x="{legend_x + 28}" y="{y + 5:.1f}" font-size="12" fill="#495057">{value:.2f}</text>'
        )

    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            '<rect width="100%" height="100%" fill="#ffffff" />',
            f'<text x="{margin_left}" y="30" font-size="24" font-weight="bold" fill="#212529">{title}</text>',
            *cells,
            *x_labels,
            *y_labels,
            *legend_items,
            f'<text x="{margin_left + plot_width / 2:.1f}" y="{height - 28}" font-size="12" text-anchor="middle" fill="#495057">{x_label}</text>',
            f'<text x="30" y="{margin_top + plot_height / 2:.1f}" font-size="12" fill="#495057" transform="rotate(-90 30 {margin_top + plot_height / 2:.1f})">{y_label}</text>',
            "</svg>",
        ]
    )


def _heatmap_color(value: float, min_value: float, max_value: float) -> str:
    ratio = (value - min_value) / (max_value - min_value)
    red = int(240 - 120 * ratio)
    green = int(245 - 40 * ratio)
    blue = int(255 - 180 * ratio)
    return f"rgb({red},{green},{blue})"
