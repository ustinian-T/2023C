%% Q1 academic figures (MATLAB only)
% Numerical results are read from Python-generated CSV files.  This script
% performs visualization only and does not refit any model.

clear; close all; clc;
rng(20230907, 'twister');

scriptPath = mfilename('fullpath');
rootDir = fileparts(fileparts(scriptPath));
outputDir = fullfile(rootDir, 'outputs');
tableDir = fullfile(outputDir, 'tables');
figureDir = fullfile(outputDir, 'figures');
if ~exist(figureDir, 'dir'), mkdir(figureDir); end

fontName = 'Microsoft YaHei';

% Unified SCI palette supplied by the user (RGB values are exact).
% Light tones encode context/weak evidence; blue-green and blue families
% encode positive and negative relations respectively. Marker shape and line
% style remain redundant encodings for grayscale and color-vision robustness.
paleMint = [221 242 240] / 255;  % #DDF2F0
iceMint  = [214 246 241] / 255;  % #D6F6F1
mint     = [166 235 221] / 255;  % #A6EBDD
teal     = [136 201 208] / 255;  % #88C9D0
lavender = [146 158 210] / 255;  % #929ED2
blue     = [ 94 140 190] / 255;  % #5E8CBE
navy     = [ 62  86 130] / 255;  % #3E5682
dark     = [ 15  22  51] / 255;  % #0F1633

set(groot, 'defaultAxesFontName', fontName, ...
    'defaultTextFontName', fontName, ...
    'defaultAxesFontSize', 14, ...
    'defaultAxesLineWidth', 1.1, ...
    'defaultLineLineWidth', 1.8, ...
    'defaultFigureColor', 'w', ...
    'defaultAxesColor', 'w', ...
    'defaultAxesXColor', dark, ...
    'defaultAxesYColor', dark, ...
    'defaultAxesGridColor', paleMint, ...
    'defaultAxesGridAlpha', 0.75, ...
    'defaultTextColor', dark, ...
    'defaultAxesToolbarVisible', 'off');

%% Figure 1: representative MSTL decomposition
T = readtable(fullfile(tableDir, 'tab_q1_stl_example.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve', 'Encoding', 'UTF-8');
T.date = datetime(T.date, 'InputFormat', 'yyyy-MM-dd');
itemName = T.sku_name(1);

fig = figure('Position', [80 60 1500 1050]);
tl = tiledlayout(fig, 4, 1, 'TileSpacing', 'compact', 'Padding', 'compact');

ax = nexttile(tl);
plot(ax, T.date, T.sales_qty_kg, '-', 'Color', blue, 'LineWidth', 1.8);
ylabel(ax, '日销量/kg', 'FontSize', 15);
title(ax, sprintf('%s：原始日销量', itemName), 'FontSize', 17, 'FontWeight', 'bold');
legend(ax, '原始销量', 'Location', 'northeast', 'FontSize', 13, 'Box', 'off');
grid(ax, 'on');

ax = nexttile(tl);
plot(ax, T.date, T.log_sales, '-', 'Color', lavender, 'LineWidth', 1.1); hold(ax, 'on');
plot(ax, T.date, T.trend, '--', 'Color', navy, 'LineWidth', 2.4);
ylabel(ax, 'log(1+销量)', 'FontSize', 15);
legend(ax, {'变换后销量', '长期趋势'}, 'Location', 'northeast', 'FontSize', 13, 'Box', 'off');
grid(ax, 'on');

ax = nexttile(tl);
plot(ax, T.date, T.seasonal_7, '-', 'Color', blue, 'LineWidth', 1.8); hold(ax, 'on');
plot(ax, T.date, T.seasonal_365, '--', 'Color', navy, 'LineWidth', 2.0);
ylabel(ax, '季节分量', 'FontSize', 15);
legend(ax, {'7 日周期', '365 日周期'}, 'Location', 'northeast', 'FontSize', 13, 'Box', 'off');
grid(ax, 'on');

ax = nexttile(tl);
plot(ax, T.date, T.residual, '-', 'Color', dark, 'LineWidth', 1.4); hold(ax, 'on');
yline(ax, 0, ':', 'Color', blue, 'LineWidth', 1.5);
xlabel(ax, '日期', 'FontSize', 15);
ylabel(ax, '残差销量', 'FontSize', 15);
legend(ax, {'最终残差', '零基线'}, 'Location', 'northeast', 'FontSize', 13, 'Box', 'off');
grid(ax, 'on');
title(tl, 'MSTL 多季节分解：从原始销量到短期残差', 'FontSize', 19, 'FontWeight', 'bold');
annotation(fig, 'textbox', [0.72 0.915 0.25 0.045], ...
    'String', '周期：7 日与 365 日；白底为 600 dpi 输出', ...
    'HorizontalAlignment', 'right', 'VerticalAlignment', 'top', ...
    'FontName', fontName, 'FontSize', 12, 'EdgeColor', 'none', 'Color', dark);
exportAcademic(fig, figureDir, 'fig_q1_stl_decomposition');

%% Figure 2: category sales distributions and selected parametric fits
C = readtable(fullfile(tableDir, 'tab_q1_category_daily_sales.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve', 'Encoding', 'UTF-8');
D = readtable(fullfile(tableDir, 'tab_q1_distribution_summary.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve', 'Encoding', 'UTF-8');
F = readtable(fullfile(tableDir, 'tab_q1_distribution_candidates.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve', 'Encoding', 'UTF-8');
categoryNames = string(C.Properties.VariableNames(2:end));

fig = figure('Position', [60 45 1600 980]);
tl = tiledlayout(fig, 2, 3, 'TileSpacing', 'compact', 'Padding', 'compact');
for k = 1:numel(categoryNames)
    name = categoryNames(k);
    ax = nexttile(tl);
    x = C.(name);
    x = x(isfinite(x) & x > 0);
    histogram(ax, x, 24, 'Normalization', 'pdf', 'FaceColor', teal, ...
        'FaceAlpha', 0.65, 'EdgeColor', navy, 'LineWidth', 0.55); hold(ax, 'on');
    srow = D(D.level == "category" & D.item_name == name, :);
    best = srow.best_distribution(1);
    frow = F(F.level == "category" & F.item_name == name & F.distribution == best, :);
    xmax = prctile(x, 99.5);
    xx = linspace(max(0, min(x)), xmax, 400);
    yy = distributionPdf(xx, best, frow.parameter_1(1), frow.parameter_2(1));
    plot(ax, xx, yy, '-', 'Color', navy, 'LineWidth', 2.6);
    xlim(ax, [0 xmax]);
    xlabel(ax, '正销量/kg', 'FontSize', 14);
    ylabel(ax, '概率密度', 'FontSize', 14);
    title(ax, name, 'FontSize', 17, 'FontWeight', 'bold');
    legend(ax, {'经验直方图', best + " 拟合"}, 'Location', 'northeast', ...
        'FontSize', 12, 'Box', 'off');
    note = sprintf('零销量比例 %.1f%%\nKS p=%.3f', ...
        100*srow.zero_share(1), srow.best_ks_p_value(1));
    text(ax, 0.98, 0.62, note, 'Units', 'normalized', ...
        'HorizontalAlignment', 'right', 'VerticalAlignment', 'top', ...
        'FontSize', 12, 'Color', dark, 'BackgroundColor', [1 1 1 0.75]);
    grid(ax, 'on');
end
title(tl, '六类蔬菜日销量的两部分布：零质量 + 正销量条件分布', ...
    'FontSize', 19, 'FontWeight', 'bold');
exportAcademic(fig, figureDir, 'fig_q1_category_distributions');

%% Figure 3: MIC screening and conditional association
P = readtable(fullfile(tableDir, 'tab_q1_sku_pair_measures.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve', 'Encoding', 'UTF-8');
finalMask = asLogical(P.final_stable_edge);
candidateMask = asLogical(P.mic_candidate);
positiveMask = finalMask & P.partial_corr > 0;
negativeMask = finalMask & P.partial_corr < 0;
micThreshold = min(P.mic_approx(candidateMask));

fig = figure('Position', [120 80 1250 900]);
ax = axes(fig); hold(ax, 'on');
scatter(ax, P.mic_approx, P.partial_corr, 20, paleMint, 'filled', ...
    'MarkerEdgeColor', lavender, 'MarkerFaceAlpha', 0.38, ...
    'MarkerEdgeAlpha', 0.50, 'DisplayName', '全部商品对');
scatter(ax, P.mic_approx(candidateMask & ~finalMask), ...
    P.partial_corr(candidateMask & ~finalMask), 52, 'o', ...
    'MarkerEdgeColor', navy, 'LineWidth', 1.5, 'DisplayName', '仅通过 MIC');
scatter(ax, P.mic_approx(positiveMask), P.partial_corr(positiveMask), ...
    95, mint, '^', 'filled', 'MarkerEdgeColor', dark, 'LineWidth', 1.0, ...
    'DisplayName', '稳定正边');
scatter(ax, P.mic_approx(negativeMask), P.partial_corr(negativeMask), ...
    95, dark, 'v', 'filled', 'MarkerEdgeColor', dark, 'LineWidth', 1.0, ...
    'DisplayName', '稳定负边');
xline(ax, micThreshold, '--', 'MIC 99% 阈值', 'Color', dark, ...
    'LabelOrientation', 'horizontal', 'LabelVerticalAlignment', 'bottom', ...
    'FontSize', 13, 'LineWidth', 1.4, 'HandleVisibility', 'off');
yline(ax, 0, ':', 'Color', dark, 'LineWidth', 1.1, 'HandleVisibility', 'off');
xlabel(ax, '近似最大信息系数（MIC）', 'FontSize', 16);
ylabel(ax, 'Graphical Lasso 条件相关', 'FontSize', 16);
title(ax, '非线性候选关系与条件关联的双重筛选', 'FontSize', 19, 'FontWeight', 'bold');
legend(ax, 'Location', 'northeast', 'FontSize', 13, 'Box', 'off');
grid(ax, 'on'); box(ax, 'on');
text(ax, 0.98, 0.60, sprintf('MIC 候选：%d 条\n最终稳定边：%d 条\n正/负：%d/%d', ...
    sum(candidateMask), sum(finalMask), sum(positiveMask), sum(negativeMask)), ...
    'Units', 'normalized', 'HorizontalAlignment', 'right', ...
    'VerticalAlignment', 'top', 'FontSize', 13, 'BackgroundColor', 'w', ...
    'Margin', 6, 'Color', dark);
exportAcademic(fig, figureDir, 'fig_q1_mic_graphical_lasso');

%% Figure 4: stable SKU association network
N = readtable(fullfile(tableDir, 'tab_q1_sku_node_metrics.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve', 'Encoding', 'UTF-8');
E = readtable(fullfile(tableDir, 'tab_q1_sku_network_edges.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve', 'Encoding', 'UTF-8');
connected = N(N.degree > 0, :);
nodeCodes = connected.item_code;
G = graph([], [], [], cellstr(string(nodeCodes)));
G = addedge(G, cellstr(string(E.source_code)), cellstr(string(E.target_code)), abs(E.partial_corr));
[categoryList, ~, categoryIndex] = unique(connected.category_name, 'stable');
palette = [iceMint; mint; teal; lavender; blue; navy];
palette = palette(1:numel(categoryList), :);
categoryMarkers = {'o', 's', '^', 'd', 'v', '>'};

fig = figure('Position', [90 50 1450 980]);
ax = axes(fig); hold(ax, 'on');
gp = plot(ax, G, 'Layout', 'force', 'Iterations', 120, ...
    'NodeCData', categoryIndex, 'MarkerSize', 0.1, ...
    'NodeLabel', connected.item_name, 'NodeFontSize', 12, ...
    'NodeFontName', fontName);
xSpan = max(gp.XData) - min(gp.XData);
ySpan = max(gp.YData) - min(gp.YData);
gp.LineWidth = 1.5;
gp.EdgeColor = 'none';
edgeWidths = 1.2 + 4.5*rescale(abs(E.partial_corr));
for r = 1:height(E)
    sourceIdx = find(string(G.Nodes.Name) == string(E.source_code(r)), 1);
    targetIdx = find(string(G.Nodes.Name) == string(E.target_code(r)), 1);
    edgeColor = dark; edgeStyle = '--';
    if E.partial_corr(r) > 0
        edgeColor = teal; edgeStyle = '-';
    end
    plot(ax, gp.XData([sourceIdx targetIdx]), gp.YData([sourceIdx targetIdx]), ...
        edgeStyle, 'Color', edgeColor, 'LineWidth', edgeWidths(r), ...
        'HandleVisibility', 'off');
end
uistack(gp, 'top');
for k = 1:numel(categoryList)
    nodeMask = categoryIndex == k;
    scatter(ax, gp.XData(nodeMask), gp.YData(nodeMask), 95, ...
        categoryMarkers{k}, 'filled', 'MarkerFaceColor', palette(k,:), ...
        'MarkerEdgeColor', dark, 'LineWidth', 0.8, ...
        'HandleVisibility', 'off');
end
% Apply layout padding after all highlight calls because GraphPlot can restore
% automatic limits while edge styles are updated.
ax.Position = [0.06 0.08 0.67 0.82];
xlim(ax, [min(gp.XData)-0.28*xSpan, max(gp.XData)+0.28*xSpan]);
ylim(ax, [min(gp.YData)-0.18*ySpan, max(gp.YData)+0.18*ySpan]);
colormap(ax, palette);
axis(ax, 'off');
title(ax, '高活跃单品的稳定稀疏条件关联网络', 'FontSize', 20, 'FontWeight', 'bold');

h = gobjects(numel(categoryList) + 2, 1);
labels = strings(numel(categoryList) + 2, 1);
for k = 1:numel(categoryList)
    h(k) = scatter(ax, nan, nan, 90, categoryMarkers{k}, 'filled', ...
        'MarkerFaceColor', palette(k,:), 'MarkerEdgeColor', dark, ...
        'LineWidth', 0.8);
    labels(k) = categoryList(k);
end
h(end-1) = plot(ax, nan, nan, '-', 'Color', teal, 'LineWidth', 2.8);
h(end) = plot(ax, nan, nan, '--', 'Color', dark, 'LineWidth', 2.8);
labels(end-1:end) = ["潜在互补/同步", "潜在替代"];
lg = legend(ax, h, labels, 'Location', 'northeast', 'FontSize', 11, 'Box', 'on');
lg.Position = [0.76 0.43 0.21 0.31];
annotation(fig, 'textbox', [0.73 0.80 0.25 0.12], ...
    'String', sprintf('47 个入选单品\n%d 个连通节点，%d 条稳定边\n孤立节点未绘制', ...
    height(connected), height(E)), 'HorizontalAlignment', 'right', ...
    'VerticalAlignment', 'top', 'FontName', fontName, 'FontSize', 12, ...
    'BackgroundColor', 'w', 'EdgeColor', paleMint, 'Margin', 6);
exportAcademic(fig, figureDir, 'fig_q1_sku_network');

%% Figure 5: category conditional-correlation matrix
CP = readtable(fullfile(tableDir, 'tab_q1_category_pair_measures.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve', 'Encoding', 'UTF-8');
catNames = unique([CP.source_code; CP.target_code], 'stable');
M = eye(numel(catNames));
stableM = false(numel(catNames), numel(catNames));
for r = 1:height(CP)
    i = find(catNames == CP.source_code(r), 1);
    j = find(catNames == CP.target_code(r), 1);
    M(i,j) = CP.partial_corr(r); M(j,i) = CP.partial_corr(r);
    stableM(i,j) = asLogical(CP.final_stable_edge(r));
    stableM(j,i) = stableM(i,j);
end

fig = figure('Position', [180 80 1050 900]);
ax = axes(fig);
imagesc(ax, M, [-0.4 0.4]); axis(ax, 'square');
set(ax, 'XTick', 1:numel(catNames), 'XTickLabel', catNames, ...
    'YTick', 1:numel(catNames), 'YTickLabel', catNames, ...
    'XTickLabelRotation', 25, 'FontSize', 14);
colormap(ax, divergingMap(256));
cb = colorbar(ax); cb.Label.String = '条件相关系数'; cb.FontSize = 13;
xlabel(ax, '品类', 'FontSize', 15); ylabel(ax, '品类', 'FontSize', 15);
title(ax, '品类层 Graphical Lasso 条件相关矩阵', 'FontSize', 19, 'FontWeight', 'bold');
for i = 1:numel(catNames)
    for j = 1:numel(catNames)
        if i == j
            label = '1.00';
        elseif stableM(i,j)
            label = sprintf('%.2f*', M(i,j));
        else
            label = sprintf('%.2f', M(i,j));
        end
        color = dark; if M(i,j) < -0.20, color = 'w'; end
        text(ax, j, i, label, 'HorizontalAlignment', 'center', ...
            'FontSize', 13, 'FontWeight', 'bold', 'Color', color);
    end
end
annotation(fig, 'textbox', [0.57 0.895 0.31 0.045], ...
    'String', '* 同时通过 MIC 与稳定性筛选', ...
    'HorizontalAlignment', 'right', 'VerticalAlignment', 'top', ...
    'FontName', fontName, 'FontSize', 12, 'Color', dark, ...
    'BackgroundColor', 'w', 'EdgeColor', 'none', 'Margin', 2);
exportAcademic(fig, figureDir, 'fig_q1_category_partial_matrix');

%% Figure 6: EBIC path and bootstrap stability
A = readtable(fullfile(tableDir, 'tab_q1_sku_alpha_path.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve', 'Encoding', 'UTF-8');
S = readtable(fullfile(tableDir, 'tab_q1_sku_sensitivity.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve', 'Encoding', 'UTF-8');
[~, bestIdx] = min(A.ebic);

fig = figure('Position', [100 60 1450 850]);
tl = tiledlayout(fig, 1, 2, 'TileSpacing', 'compact', 'Padding', 'compact');
ax = nexttile(tl); hold(ax, 'on');
semilogx(ax, A.alpha, A.ebic, '-o', 'Color', blue, 'MarkerSize', 5, ...
    'MarkerFaceColor', blue, 'DisplayName', 'EBIC');
scatter(ax, A.alpha(bestIdx), A.ebic(bestIdx), 110, dark, 'filled', ...
    'DisplayName', '最优正则强度');
xlabel(ax, 'Graphical Lasso 正则强度 \lambda', 'FontSize', 15);
ylabel(ax, 'EBIC', 'FontSize', 15);
title(ax, 'EBIC 正则路径', 'FontSize', 18, 'FontWeight', 'bold');
legend(ax, 'Location', 'northeast', 'FontSize', 13, 'Box', 'off');
grid(ax, 'on');

ax = nexttile(tl); hold(ax, 'on');
stableCandidate = candidateMask & asLogical(P.graphical_lasso_edge);
histogram(ax, P.bootstrap_same_sign_rate(stableCandidate), 0:0.05:1, ...
    'FaceColor', teal, 'FaceAlpha', 0.78, 'EdgeColor', navy, 'LineWidth', 0.8, ...
    'DisplayName', '候选边同号稳定率');
xline(ax, 0.70, '--', '70% 门槛', 'Color', dark, 'LineWidth', 1.6, ...
    'FontSize', 13, 'LabelVerticalAlignment', 'bottom', 'HandleVisibility', 'off');
xlabel(ax, '移动块 Bootstrap 同号稳定率', 'FontSize', 15);
ylabel(ax, '边数', 'FontSize', 15);
title(ax, '最终边的稳定性证据', 'FontSize', 18, 'FontWeight', 'bold');
legend(ax, 'Location', 'northeast', 'FontSize', 13, 'Box', 'off');
grid(ax, 'on');
title(tl, '模型选择与稳健性检验', 'FontSize', 20, 'FontWeight', 'bold');
text(ax, 0.98, 0.72, sprintf('正则强度 lambda=%.3f\nlambda 的 ±20%% 下边集合不变', A.alpha(bestIdx)), ...
    'Units', 'normalized', 'HorizontalAlignment', 'right', 'VerticalAlignment', 'top', ...
    'FontName', fontName, 'FontSize', 13, 'BackgroundColor', 'w', ...
    'EdgeColor', paleMint, 'Margin', 6);
exportAcademic(fig, figureDir, 'fig_q1_robustness');

fprintf('Generated six Q1 academic figures in %s\n', figureDir);

%% Local functions
function y = distributionPdf(x, name, p1, p2)
    switch string(name)
        case "Normal"
            y = normpdf(x, p1, p2);
        case "Lognormal"
            y = lognpdf(x, log(p2), p1);
        case "Gamma"
            y = gampdf(x, p1, p2);
        case "Weibull"
            y = wblpdf(x, p2, p1);
        otherwise
            y = nan(size(x));
    end
end

function out = asLogical(value)
    if islogical(value)
        out = value;
    elseif isnumeric(value)
        out = value ~= 0;
    else
        textValue = lower(strtrim(string(value)));
        out = textValue == "true" | textValue == "1" | textValue == "yes";
    end
end

function cmap = divergingMap(n)
    negative = [62 86 130] / 255;   % #3E5682
    center = [1 1 1];
    positive = [166 235 221] / 255; % #A6EBDD
    n1 = floor(n/2);
    n2 = n - n1;
    cmap = [linspace(negative(1),center(1),n1)' linspace(negative(2),center(2),n1)' linspace(negative(3),center(3),n1)'; ...
            linspace(center(1),positive(1),n2)' linspace(center(2),positive(2),n2)' linspace(center(3),positive(3),n2)'];
end

function exportAcademic(fig, figureDir, baseName)
    drawnow;
    pngPath = fullfile(figureDir, baseName + ".png");
    pdfPath = fullfile(figureDir, baseName + ".pdf");
    exportgraphics(fig, pngPath, 'Resolution', 600, 'BackgroundColor', 'white');
    exportgraphics(fig, pdfPath, 'ContentType', 'vector', 'BackgroundColor', 'white');

    % MATLAB-only grayscale simulation for paper-print QA.  The main figure
    % remains the color PNG/PDF; this preview verifies luminance, line-style,
    % marker-shape and annotation discrimination without changing the data.
    previewDir = fullfile(figureDir, 'print_preview');
    if ~exist(previewDir, 'dir'), mkdir(previewDir); end
    colorImage = imread(pngPath);
    grayImage = rgb2gray(colorImage);
    previewPath = fullfile(previewDir, baseName + "_bw_preview.png");
    imwrite(grayImage, previewPath, 'ResolutionUnit', 'meter', ...
        'XResolution', 23622, 'YResolution', 23622);
end
