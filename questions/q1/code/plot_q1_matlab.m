%% Q1 论文图表（MATLAB）
% 结论导向的六组图：分布、季节规律、k 选择、聚类画像、分层关系、代表单品。
% 全部统计量直接读取 Python 已生成的结果表，不在绘图脚本中重新拟合模型。

clear; close all; clc;
rng(20230907, 'twister');

scriptPath = mfilename('fullpath');
rootDir = fileparts(fileparts(scriptPath));
projectDir = fileparts(fileparts(rootDir));
tableDir = fullfile(rootDir, 'outputs', 'tables');
figureDir = fullfile(rootDir, 'outputs', 'figures');
previewDir = fullfile(figureDir, 'print_preview');
dataDir = fullfile(projectDir, 'data', 'processed');
if ~exist(figureDir, 'dir'), mkdir(figureDir); end
if ~exist(previewDir, 'dir'), mkdir(previewDir); end

fontName = 'Microsoft YaHei';
set(groot, 'defaultAxesFontName', fontName, ...
    'defaultAxesFontSize', 12, ...
    'defaultTextFontName', fontName, ...
    'defaultLegendFontName', fontName);

% 参考图的 Nature 风格低饱和配色。
palette = [110 143 178; 125 164 148; 234 182 122; 229 167 154; ...
           193 110 113; 171 200 229; 216 160 193; 159 141 184; ...
           208 208 138] / 255;
dark = [45 45 45] / 255;
lineStyles = {'-', '--', '-.', ':', '-', '--'};
markers = {'o', 's', '^', 'd', 'v', 'p'};

%% 图 1：六品类正销量分布（箱线 + 抖动散点）
dailyCat = readtable(fullfile(dataDir, 'processed_daily_category.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve');
catNames = unique(dailyCat.category_name, 'stable');

fig = figure('Name', '六品类正销量分布', 'NumberTitle', 'off', ...
    'Position', [50 50 2100 1250], 'Visible', 'off');
ax = axes(fig); hold(ax, 'on');
for i = 1:numel(catNames)
    vals = dailyCat.gross_sales_qty(dailyCat.category_name == catNames(i));
    vals = log10(1 + vals(vals > 0));
    x = i * ones(size(vals));
    boxchart(ax, x, vals, 'BoxFaceColor', palette(i,:), ...
        'BoxFaceAlpha', 0.30, 'WhiskerLineColor', palette(i,:), ...
        'MarkerStyle', 'none', 'LineWidth', 1.5, 'BoxWidth', 0.45);
    take = unique(round(linspace(1, numel(vals), min(90, numel(vals)))));
    jitter = 0.17 * (2 * rand(numel(take), 1) - 1);
    scatter(ax, i + jitter, vals(take), 18, palette(i,:), 'filled', ...
        'MarkerFaceAlpha', 0.46, 'MarkerEdgeAlpha', 0.30);
end
ylabel(ax, 'log_{10}(1 + 日销量/kg)');
title(ax, '六个蔬菜品类的正销量分布');
xticks(ax, 1:numel(catNames)); xticklabels(ax, catNames);
xlim(ax, [0.45 numel(catNames)+0.55]);
grid(ax, 'on'); ax.GridAlpha = 0.16; ax.Box = 'off';
exportFig(fig, fullfile(figureDir, 'fig_q1_category_distribution_box'));

%% 图 2：六品类月度季节指数曲线（保留原有优秀视觉结构）
catMonthly = readtable(fullfile(tableDir, 'tab_q1_monthly_category_profile.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve');
categories = unique(catMonthly.category_name, 'stable');

fig = figure('Name', '品类季节指数', 'NumberTitle', 'off', ...
    'Position', [50 50 2050 1250], 'Visible', 'off');
ax = axes(fig); hold(ax, 'on');
curveHandles = gobjects(numel(categories), 1);
for i = 1:numel(categories)
    d = catMonthly(catMonthly.category_name == categories(i), :);
    curveHandles(i) = plot(ax, d.month, d.seasonal_index, ...
        'LineStyle', lineStyles{i}, 'Marker', markers{i}, ...
        'LineWidth', 2.4, 'MarkerSize', 8, 'Color', palette(i,:), ...
        'MarkerFaceColor', 'white', 'DisplayName', categories(i));
end
yline(ax, 1, '--', '全年平均水平', 'Color', [0.30 0.30 0.30], ...
    'LineWidth', 1.1, 'LabelHorizontalAlignment', 'left');
xlabel(ax, '月份'); ylabel(ax, '季节指数');
title(ax, '六个蔬菜品类的月度季节指数');
xticks(ax, 1:12); xlim(ax, [1 12]);
legend(ax, curveHandles, categories, 'Location', 'northeastoutside');
grid(ax, 'on'); ax.GridAlpha = 0.16; ax.Box = 'off'; hold(ax, 'off');
exportFig(fig, fullfile(figureDir, 'fig_q1_seasonal_index_curves'));

%% 图 3：k 选择综合矩阵（替代四幅折线图）
kEval = readtable(fullfile(tableDir, 'tab_q1_cluster_k_selection.csv'), ...
    'VariableNamingRule', 'preserve');
raw = [kEval.silhouette'; kEval.calinski_harabasz'; kEval.davies_bouldin'; ...
       kEval.min_cluster_size'; kEval.bootstrap_ari_mean'];
score = zeros(size(raw));
for r = 1:size(raw,1)
    z = (raw(r,:) - min(raw(r,:))) / max(eps, max(raw(r,:)) - min(raw(r,:)));
    if r == 3, z = 1 - z; end
    score(r,:) = z;
end

fig = figure('Name', '聚类数选择', 'NumberTitle', 'off', ...
    'Position', [50 50 1950 1050], 'Visible', 'off');
ax = axes(fig);
imagesc(ax, score); colormap(ax, sequentialMap(palette(1,:), 256)); clim(ax, [0 1]);
cb = colorbar(ax); cb.Label.String = '相对优度（越大越优）';
xticks(ax, 1:height(kEval)); xticklabels(ax, compose('k=%d', kEval.k));
yticks(ax, 1:5); yticklabels(ax, {'轮廓系数','CH 指数','DB 指数', ...
    '最小簇规模','重采样 ARI'});
xlabel(ax, '候选聚类数'); title(ax, '聚类数的多指标综合比较（红框为综合选择 k=5）');
for r = 1:5
    for c = 1:height(kEval)
        if r == 4, label = sprintf('%d', round(raw(r,c)));
        else, label = sprintf('%.2f', raw(r,c)); end
        tc = dark; if score(r,c) > 0.62, tc = [1 1 1]; end
        text(ax, c, r, label, 'HorizontalAlignment', 'center', ...
            'FontWeight', 'bold', 'FontSize', 11, 'Color', tc);
    end
end
k5 = find(kEval.k == 5, 1);
rectangle(ax, 'Position', [k5-0.48 0.52 0.96 4.96], ...
    'EdgeColor', palette(5,:), 'LineWidth', 3, 'LineStyle', '-');
ax.TickLength = [0 0]; ax.Box = 'on';
exportFig(fig, fullfile(figureDir, 'fig_q1_k_selection_matrix'));

%% 图 4：五簇双画像热图（替代大量单品折线）
clusterProfiles = readtable(fullfile(tableDir, 'tab_q1_cluster_profiles.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve');
nClusters = height(clusterProfiles);
si = zeros(nClusters, 12); active = zeros(nClusters, 12);
for m = 1:12
    si(:,m) = clusterProfiles.(sprintf('seasonal_index_month_%d', m));
    active(:,m) = clusterProfiles.(sprintf('active_rate_month_%d', m));
end
clusterLabels = clusterProfiles.cluster_name + "（n=" + string(clusterProfiles.n_skus) + "）";

fig = figure('Name', '季节簇画像', 'NumberTitle', 'off', ...
    'Position', [50 50 2200 1450], 'Visible', 'off');
t = tiledlayout(fig, 2, 1, 'Padding', 'compact', 'TileSpacing', 'compact');
ax1 = nexttile(t); imagesc(ax1, si); colormap(ax1, sequentialMap(palette(6,:), 256));
cb1 = colorbar(ax1); cb1.Label.String = '季节指数';
formatClusterHeatmap(ax1, clusterLabels, '月度季节指数画像');
annotateHeatmap(ax1, si, 1.55);
ax2 = nexttile(t); imagesc(ax2, active); colormap(ax2, sequentialMap(palette(2,:), 256)); clim(ax2, [0 1]);
cb2 = colorbar(ax2); cb2.Label.String = '销售活跃率';
formatClusterHeatmap(ax2, clusterLabels, '月度销售活跃率画像');
annotateHeatmap(ax2, active, 0.58);
title(t, '五个单品季节簇的双指标画像', 'FontWeight', 'bold', 'FontSize', 16);
exportFig(fig, fullfile(figureDir, 'fig_q1_cluster_profile_heatmaps'));

%% 图 5：品类与季节簇的总量—份额关系（合并重复关系图）
catRels = readtable(fullfile(tableDir, 'tab_q1_category_pair_relationships.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve');
clusterRels = readtable(fullfile(tableDir, 'tab_q1_cluster_pair_relationships.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve');
catSales = pairMatrix(catRels, categories, 'sales_corr_全年', false);
catShare = pairMatrix(catRels, categories, 'share_corr_全年', false);
clusterIds = compose('cluster_%d', clusterProfiles.cluster_id);
clSales = pairMatrix(clusterRels, clusterIds, 'sales_corr_全年', true);
clShare = pairMatrix(clusterRels, clusterIds, 'share_corr_全年', true);

fig = figure('Name', '分层关系矩阵', 'NumberTitle', 'off', ...
    'Position', [50 50 2300 1900], 'Visible', 'off');
t = tiledlayout(fig, 2, 2, 'Padding', 'compact', 'TileSpacing', 'compact');
drawCorrMatrix(nexttile(t), catSales, categories, '六品类：全年销量相关');
drawCorrMatrix(nexttile(t), catShare, categories, '六品类：全年销量份额相关');
drawCorrMatrix(nexttile(t), clSales, clusterProfiles.cluster_name, '五季节簇：全年销量相关');
drawCorrMatrix(nexttile(t), clShare, clusterProfiles.cluster_name, '五季节簇：全年销量份额相关');
title(t, '不同层级的总量共变与结构竞争', 'FontWeight', 'bold', 'FontSize', 16);
exportFig(fig, fullfile(figureDir, 'fig_q1_hierarchical_relationships'));

%% 图 6：代表性单品对全年相关及 95% 置信区间
allSku = readtable(fullfile(tableDir, 'tab_q1_all_sku_pair_relationships.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve');
activity = readtable(fullfile(tableDir, 'tab_q1_sku_activity_filter.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve');
valid = isfinite(allSku.('sales_ci_lower_全年')) & isfinite(allSku.('sales_ci_upper_全年')) ...
    & abs(allSku.('sales_corr_全年')) >= 0.30;
candidates = allSku(valid,:);
pos = candidates(candidates.('sales_corr_全年') > 0, :);
neg = candidates(candidates.('sales_corr_全年') < 0, :);
[~, pOrder] = sort(pos.('sales_corr_全年'), 'descend');
[~, nOrder] = sort(neg.('sales_corr_全年'), 'ascend');
nNeg = min(3, height(neg));
nPos = min(7, height(pos));
top = [neg(nOrder(1:nNeg), :); pos(pOrder(1:nPos), :)];
[rho, idx] = sort(top.('sales_corr_全年'), 'ascend'); top = top(idx,:);
lower = top.('sales_ci_lower_全年'); upper = top.('sales_ci_upper_全年');
labels = strings(height(top), 1);
codes = normalizeCodeVector(activity.sku_code);
for i = 1:height(top)
    src = normalizeCode(top.source(i)); tgt = normalizeCode(top.target(i));
    srcName = activity.sku_name(codes == src); tgtName = activity.sku_name(codes == tgt);
    if isempty(srcName), srcName = src; end
    if isempty(tgtName), tgtName = tgt; end
    labels(i) = srcName(1) + "—" + tgtName(1);
end

fig = figure('Name', '代表单品关系', 'NumberTitle', 'off', ...
    'Position', [50 50 2100 1350], 'Visible', 'off');
ax = axes(fig); hold(ax, 'on'); y = (1:height(top))';
for i = 1:height(top)
    c = palette(1,:); marker = 'o';
    if rho(i) < 0, c = palette(5,:); marker = 's'; end
    plot(ax, [lower(i) upper(i)], [y(i) y(i)], '-', 'Color', c, 'LineWidth', 2.3);
    plot(ax, rho(i), y(i), marker, 'Color', c, 'MarkerFaceColor', c, ...
        'MarkerSize', 8, 'LineWidth', 1.2);
end
xline(ax, 0, '--', '零相关', 'Color', [0.35 0.35 0.35], 'LineWidth', 1.2);
yticks(ax, y); yticklabels(ax, labels); ylim(ax, [0.4 height(top)+0.6]);
xlabel(ax, '全年 Spearman 相关系数（95% CI）');
title(ax, '代表性单品对的全年销量关系');
grid(ax, 'on'); ax.GridAlpha = 0.15; ax.YGrid = 'off'; ax.Box = 'off';
hold(ax, 'off');
exportFig(fig, fullfile(figureDir, 'fig_q1_representative_pairs'));

fprintf('已生成 6 组论文图表：%s\n', figureDir);

%% 辅助函数
function exportFig(fig, basePath)
    set(fig, 'Color', 'white');
    drawnow;
    print(fig, basePath + ".png", '-dpng', '-r600');
    print(fig, basePath + ".pdf", '-dpdf', '-bestfit');
    [p, f] = fileparts(basePath);
    previewDir = fullfile(p, 'print_preview');
    if ~exist(previewDir, 'dir'), mkdir(previewDir); end
    temp = fullfile(previewDir, f + "_temp.png");
    print(fig, temp, '-dpng', '-r180');
    gray = rgb2gray(imread(temp));
    imwrite(gray, fullfile(previewDir, f + "_bw_preview.png"));
    delete(temp); close(fig);
end

function cmap = sequentialMap(color, n)
    if nargin < 2, n = 256; end
    white = [1 1 1];
    cmap = [linspace(white(1),color(1),n)', ...
            linspace(white(2),color(2),n)', ...
            linspace(white(3),color(3),n)'];
end

function cmap = divergingMap(n)
    if nargin < 1, n = 256; end
    neg = [110 143 178]/255; mid = [1 1 1]; pos = [193 110 113]/255;
    h = floor(n/2);
    cmap = [linspace(neg(1),mid(1),h)', linspace(neg(2),mid(2),h)', linspace(neg(3),mid(3),h)'; ...
            linspace(mid(1),pos(1),n-h)', linspace(mid(2),pos(2),n-h)', linspace(mid(3),pos(3),n-h)'];
end

function formatClusterHeatmap(ax, labels, ttl)
    xticks(ax, 1:12); xticklabels(ax, compose('%d月', 1:12));
    yticks(ax, 1:numel(labels)); yticklabels(ax, labels);
    xlabel(ax, '月份'); title(ax, ttl); ax.TickLength = [0 0]; ax.Box = 'on';
end

function annotateHeatmap(ax, mat, cutoff)
    for r = 1:size(mat,1)
        for c = 1:size(mat,2)
            tc = [0.18 0.18 0.18]; if mat(r,c) >= cutoff, tc = [1 1 1]; end
            text(ax, c, r, sprintf('%.2f', mat(r,c)), ...
                'HorizontalAlignment', 'center', 'FontSize', 8.5, 'Color', tc);
        end
    end
end

function mat = pairMatrix(tbl, labels, colName, clusterMode)
    n = numel(labels); mat = eye(n);
    for r = 1:height(tbl)
        src = string(tbl.source(r)); tgt = string(tbl.target(r));
        if clusterMode
            si = find(labels == src, 1); ti = find(labels == tgt, 1);
        else
            si = find(labels == src, 1); ti = find(labels == tgt, 1);
        end
        if ~isempty(si) && ~isempty(ti)
            mat(si,ti) = tbl.(colName)(r); mat(ti,si) = tbl.(colName)(r);
        end
    end
end

function drawCorrMatrix(ax, mat, labels, ttl)
    imagesc(ax, mat); colormap(ax, divergingMap(256)); clim(ax, [-1 1]);
    colorbar(ax); xticks(ax, 1:numel(labels)); xticklabels(ax, labels); xtickangle(ax, 25);
    yticks(ax, 1:numel(labels)); yticklabels(ax, labels); title(ax, ttl);
    ax.TickLength = [0 0]; ax.Box = 'on';
    for i = 1:size(mat,1)
        for j = 1:size(mat,2)
            tc = [0.18 0.18 0.18]; if abs(mat(i,j)) > 0.58, tc = [1 1 1]; end
            text(ax, j, i, sprintf('%+.2f', mat(i,j)), ...
                'HorizontalAlignment', 'center', 'FontWeight', 'bold', ...
                'FontSize', 9, 'Color', tc);
        end
    end
end

function code = normalizeCode(value)
    if isnumeric(value), code = string(sprintf('%.0f', value));
    else, code = string(value); end
end

function codes = normalizeCodeVector(values)
    if isnumeric(values), codes = string(compose('%.0f', values));
    else, codes = string(values); end
end
