%% Q1 redesigned academic figures (MATLAB only)
% Seasonal clustering + hierarchical relationship analysis.
% Reads Python-generated CSVs; does NOT refit models.
%
% Figures:
%   1. Six-category simplified distribution plots
%   2. Six-category 12-month seasonal index curves
%   3. k=2-8 clustering evaluation & stability
%   4. Five cluster centers: monthly/seasonal profiles
%   5. Six-category four-season relationship heatmaps
%   6. Five cluster between-cluster relationship heatmaps
%   7. Representative within-cluster or within-category SKU pair plots

clear; close all; clc;
rng(20230907, 'twister');

scriptPath = mfilename('fullpath');
rootDir = fileparts(fileparts(scriptPath));
outputDir = fullfile(rootDir, 'outputs');
tableDir = fullfile(outputDir, 'tables');
figureDir = fullfile(outputDir, 'figures');
if ~exist(figureDir, 'dir'), mkdir(figureDir); end

fontName = 'Microsoft YaHei';

% User-specified green-orange-blue-purple palette.  Line styles and markers
% are deliberately redundant so curves remain distinguishable in grayscale.
sage       = [153 188 153] / 255;  % #99BC99
peach      = [255 204 153] / 255;  % #FFCC99
powderBlue = [153 187 222] / 255;  % #99BBDE
softPurple = [182 182 255] / 255;  % #B6B6FF
deepTeal   = [ 19 103 100] / 255;  % #136764
coral      = [255 165 121] / 255;  % #FFA579
strongBlue = [ 62 133 197] / 255;  % #3E85C5
purple     = [162 162 255] / 255;  % #A2A2FF
dark       = [ 36  45  56] / 255;

clusterColors = [deepTeal; coral; strongBlue; purple; sage; peach];
seasonNames = {'Spring', 'Summer', 'Autumn', 'Winter'};
seasonNamesCN = {'春季', '夏季', '秋季', '冬季'};

set(groot, 'defaultAxesFontName', fontName, ...
    'defaultAxesFontSize', 12, ...
    'defaultTextFontName', fontName);

figCount = 0;

% =======================================================================
% FIGURE 1: Six-category distribution summary
% =======================================================================
try
    distSum = readtable(fullfile(tableDir, 'tab_q1_distribution_summary.csv'), ...
        'TextType', 'string');
    catRows = distSum(distSum.level == "category", :);

    figCount = figCount + 1;
    fig = figure('Name', 'Category Distributions', 'NumberTitle', 'off', ...
        'Position', [50 50 2400 1600], 'Visible', 'off');
    tiledlayout(2, 3, 'Padding', 'compact', 'TileSpacing', 'compact');

    for idx = 1:height(catRows)
        nexttile;
        row = catRows(idx, :);
        % Bar chart: zero share vs positive
        b = bar([row.zero_share, 1-row.zero_share], 'FaceColor', 'flat', ...
            'EdgeColor', dark, 'LineWidth', 1.0);
        b.CData = [sage; strongBlue];
        title(sprintf('%s', row.item_name));
        ylabel('Proportion');
        % X labels already identify the two bars; omit a redundant legend.
        subtitle(sprintf('Best: %s (AIC=%.1f, KS p=%.3f)', ...
            row.best_distribution, row.best_aic, row.best_ks_p_value));
        set(gca, 'XTickLabel', {'Zero', 'Positive'});
    end

    exportFig(fig, fullfile(figureDir, 'fig_q1_category_distributions'));
catch ME
    warning('Figure 1 failed: %s', ME.message);
end

% =======================================================================
% FIGURE 2: Six-category 12-month seasonal index curves
% =======================================================================
try
    catMonthly = readtable(fullfile(tableDir, 'tab_q1_monthly_category_profile.csv'), ...
        'TextType', 'string');
    categories = unique(catMonthly.category_name, 'stable');

    figCount = figCount + 1;
    fig = figure('Name', 'Seasonal Index Curves', 'NumberTitle', 'off', ...
        'Position', [50 50 2000 1400], 'Visible', 'off');
    hold on;
    lineStyles = {'-', '--', '-.', ':', '-', '--'};
    markers = {'o', 's', '^', 'd', 'v', 'p'};
    curveHandles = gobjects(length(categories), 1);
    for i = 1:length(categories)
        cat = categories(i);
        catData = catMonthly(catMonthly.category_name == cat, :);
        curveHandles(i) = plot(catData.month, catData.seasonal_index, ...
            'LineStyle', lineStyles{i}, 'Marker', markers{i}, ...
            'LineWidth', 2, 'MarkerSize', 8, ...
            'Color', clusterColors(mod(i-1, size(clusterColors,1))+1, :), ...
            'DisplayName', sprintf('%s', cat));
    end
    yline(1.0, 'k--', 'LineWidth', 1);
    xlabel('Month'); ylabel('Seasonal Index');
    title('Six Categories: 12-Month Seasonal Index');
    legend(curveHandles, categories, 'Location', 'northeastoutside', 'NumColumns', 1);
    xlim([1 12]); xticks(1:12);
    grid on; hold off;
    exportFig(fig, fullfile(figureDir, 'fig_q1_seasonal_index_curves'));
catch ME
    warning('Figure 2 failed: %s', ME.message);
end

% =======================================================================
% FIGURE 3: k=2-8 clustering evaluation & stability
% =======================================================================
try
    kEval = readtable(fullfile(tableDir, 'tab_q1_cluster_k_selection.csv'));

    figCount = figCount + 1;
    fig = figure('Name', 'K Selection', 'NumberTitle', 'off', ...
        'Position', [50 50 2400 1600], 'Visible', 'off');
    tiledlayout(2, 2, 'Padding', 'compact', 'TileSpacing', 'compact');

    % Silhouette
    nexttile;
    plot(kEval.k, kEval.silhouette, 'o-', 'LineWidth', 2, ...
        'Color', deepTeal, 'MarkerFaceColor', 'white', 'MarkerSize', 10);
    xlabel('k'); ylabel('Silhouette Score');
    title('Silhouette Score (higher better)');
    grid on;

    % Calinski-Harabasz
    nexttile;
    plot(kEval.k, kEval.calinski_harabasz, 's-', 'LineWidth', 2, ...
        'Color', strongBlue, 'MarkerFaceColor', strongBlue, 'MarkerSize', 10);
    xlabel('k'); ylabel('Calinski-Harabasz');
    title('CH Score (higher better)');
    grid on;

    % Davies-Bouldin
    nexttile;
    plot(kEval.k, kEval.davies_bouldin, 'd-', 'LineWidth', 2, ...
        'Color', coral, 'MarkerFaceColor', 'white', 'MarkerSize', 10);
    xlabel('k'); ylabel('Davies-Bouldin');
    title('DB Score (lower better)');
    grid on;

    % Bootstrap ARI
    nexttile;
    errorbar(kEval.k, kEval.bootstrap_ari_mean, kEval.bootstrap_ari_std, ...
        '^--', 'LineWidth', 2, 'Color', purple, 'MarkerFaceColor', purple, 'MarkerSize', 10);
    xlabel('k'); ylabel('Bootstrap ARI');
    title('Resampling Stability (mean ARI ± 1 std)');
    grid on;

    sgtitle('K-means Clustering Evaluation (k=5 selected by combined criteria)');
    exportFig(fig, fullfile(figureDir, 'fig_q1_k_selection'));
catch ME
    warning('Figure 3 failed: %s', ME.message);
end

% =======================================================================
% FIGURE 4: Five cluster profiles (monthly + seasonal)
% =======================================================================
try
    skuClusters = readtable(fullfile(tableDir, 'tab_q1_sku_clusters.csv'), ...
        'TextType', 'string');
    clusterProfiles = readtable(fullfile(tableDir, 'tab_q1_cluster_profiles.csv'), ...
        'TextType', 'string');
    skuMonthly = readtable(fullfile(tableDir, 'tab_q1_monthly_sku_profile.csv'), ...
        'TextType', 'string');

    nClusters = height(clusterProfiles);
    figCount = figCount + 1;
    fig = figure('Name', 'Cluster Profiles', 'NumberTitle', 'off', ...
        'Position', [50 50 2400 1800], 'Visible', 'off');

    for cid = 1:nClusters
        subplot(2, 3, cid);
        % Get SKUs in this cluster
        cSkus = skuClusters.sku_code(skuClusters.cluster_id == cid - 1);
        cMonthly = skuMonthly(ismember(skuMonthly.sku_code, cSkus), :);

        % Plot individual SKU lines (faint) + cluster mean (bold)
        hold on;
        uniqueSkus = unique(cMonthly.sku_code);
        for s = 1:length(uniqueSkus)
            sData = cMonthly(cMonthly.sku_code == uniqueSkus(s), :);
            faintColor = 0.72 * [1 1 1] + 0.28 * clusterColors(cid, :);
            plot(sData.month, sData.seasonal_index, '-', ...
                'Color', faintColor, 'LineWidth', 0.6);
        end

        % Cluster mean
        cMean = groupsummary(cMonthly, 'month', 'mean', 'seasonal_index');
        meanStyles = {'o-', 's--', '^-', 'd-.', 'v-'};
        plot(cMean.month, cMean.mean_seasonal_index, meanStyles{cid}, ...
            'LineWidth', 3, 'Color', clusterColors(cid,:), ...
            'MarkerFaceColor', 'white', 'MarkerSize', 8);

        yline(1.0, 'k--', 'LineWidth', 1);
        cName = clusterProfiles.cluster_name(cid);
        title(sprintf('%s (n=%d)', cName, clusterProfiles.n_skus(cid)));
        xlabel('Month'); ylabel('Seasonal Index');
        xlim([1 12]); xticks(1:12);
        grid on; hold off;
    end
    sgtitle('Five Seasonal Clusters: Monthly Seasonal Index Profiles');
    exportFig(fig, fullfile(figureDir, 'fig_q1_cluster_profiles'));
catch ME
    warning('Figure 4 failed: %s', ME.message);
end

% =======================================================================
% FIGURE 5: Six-category four-season relationship heatmaps
% =======================================================================
try
    catMonthlyForNames = readtable(fullfile(tableDir, 'tab_q1_monthly_category_profile.csv'), ...
        'TextType', 'string');
    catNames = unique(catMonthlyForNames.category_name, 'stable');
    nCat = length(catNames);

    % Read category pair relationships
    catRels = readtable(fullfile(tableDir, 'tab_q1_category_pair_relationships.csv'), ...
        'TextType', 'string', 'VariableNamingRule', 'preserve');

    figCount = figCount + 1;
    fig = figure('Name', 'Category Relationships', 'NumberTitle', 'off', ...
        'Position', [50 50 2800 2200], 'Visible', 'off');
    tiledlayout(2, 2, 'Padding', 'compact', 'TileSpacing', 'compact');

    for s = 1:4
        season = seasonNamesCN{s};
        nexttile;

        % Build matrix from pairs
        mat = zeros(nCat, nCat);
        for i = 1:nCat
            mat(i, i) = 1;
        end
        colName = sprintf('sales_corr_%s', season);
        if any(strcmp(catRels.Properties.VariableNames, colName))
            for r = 1:height(catRels)
                src = string(catRels.source(r));
                tgt = string(catRels.target(r));
                si = find(catNames == src);
                ti = find(catNames == tgt);
                if ~isempty(si) && ~isempty(ti)
                    val = catRels.(colName)(r);
                    mat(si, ti) = val;
                    mat(ti, si) = val;
                end
            end
        end

        imagesc(mat);
        colormap(gca, greenwhitepurple(256));
        clim([-1 1]);
        colorbar;
        xticks(1:nCat); xticklabels(catNames); xtickangle(28);
        yticks(1:nCat); yticklabels(catNames);
        title(sprintf('%s Sales Correlation', season));

        % Add text
        for i = 1:nCat
            for j = 1:nCat
                if i ~= j && abs(mat(i,j)) > 0.01
                    txtColor = dark;
                    if abs(mat(i,j)) >= 0.55, txtColor = [1 1 1]; end
                    text(j, i, sprintf('%+.2f', mat(i,j)), ...
                        'HorizontalAlignment', 'center', 'FontSize', 10, ...
                        'FontWeight', 'bold', 'Color', txtColor);
                end
            end
        end
    end
    sgtitle('Six Categories: Four-Season Sales Correlation Matrices');
    exportFig(fig, fullfile(figureDir, 'fig_q1_category_relationships'));
catch ME
    warning('Figure 5 failed: %s', ME.message);
end

% =======================================================================
% FIGURE 6: Five cluster relationship heatmaps
% =======================================================================
try
    clusterRels = readtable(fullfile(tableDir, 'tab_q1_cluster_pair_relationships.csv'), ...
        'TextType', 'string', 'VariableNamingRule', 'preserve');

    clusterOrder = zeros(nClusters, 1);
    for i = 1:nClusters
        clusterOrder(i) = i - 1;
    end
    clusterLabels = clusterProfiles.cluster_name;

    figCount = figCount + 1;
    fig = figure('Name', 'Cluster Relationships', 'NumberTitle', 'off', ...
        'Position', [50 50 2800 2200], 'Visible', 'off');
    tiledlayout(2, 2, 'Padding', 'compact', 'TileSpacing', 'compact');

    for s = 1:4
        season = seasonNamesCN{s};
        nexttile;

        mat = zeros(nClusters, nClusters);
        for i = 1:nClusters
            mat(i, i) = 1;
        end
        colName = sprintf('sales_corr_%s', season);
        if any(strcmp(clusterRels.Properties.VariableNames, colName))
            for r = 1:height(clusterRels)
                src = string(clusterRels.source(r));
                tgt = string(clusterRels.target(r));
                % source/target are like "cluster_0"
                si = find(strcmp(src, sprintf('cluster_%d', clusterOrder)));
                ti = find(strcmp(tgt, sprintf('cluster_%d', clusterOrder)));
                if ~isempty(si) && ~isempty(ti)
                    val = clusterRels.(colName)(r);
                    mat(si, ti) = val;
                    mat(ti, si) = val;
                end
            end
        end

        imagesc(mat);
        colormap(gca, greenwhitepurple(256));
        clim([-1 1]);
        colorbar;
        xticks(1:nClusters); xticklabels(clusterLabels); xtickangle(28);
        yticks(1:nClusters); yticklabels(clusterLabels);
        title(sprintf('%s Cluster Sales Correlation', season));

        for i = 1:nClusters
            for j = 1:nClusters
                if i ~= j && abs(mat(i,j)) > 0.01
                    txtColor = dark;
                    if abs(mat(i,j)) >= 0.55, txtColor = [1 1 1]; end
                    text(j, i, sprintf('%+.2f', mat(i,j)), ...
                        'HorizontalAlignment', 'center', 'FontSize', 10, ...
                        'FontWeight', 'bold', 'Color', txtColor);
                end
            end
        end
    end
    sgtitle('Five Seasonal Clusters: Four-Season Sales Correlation Matrices');
    exportFig(fig, fullfile(figureDir, 'fig_q1_cluster_relationships'));
catch ME
    warning('Figure 6 failed: %s', ME.message);
end

% =======================================================================
% FIGURE 7: Representative within-cluster SKU relationships with 95% CI
% =======================================================================
try
    withinClust = readtable(fullfile(tableDir, 'tab_q1_within_cluster_pair_relationships.csv'), ...
        'TextType', 'string', 'VariableNamingRule', 'preserve');
    activity = readtable(fullfile(tableDir, 'tab_q1_sku_activity_filter.csv'), ...
        'TextType', 'string', 'VariableNamingRule', 'preserve');
    if isnumeric(activity.sku_code)
        activityCodes = string(compose('%.0f', activity.sku_code));
    else
        activityCodes = string(activity.sku_code);
    end

    figCount = figCount + 1;
    fig = figure('Name', 'Representative SKU Relationships', 'NumberTitle', 'off', ...
        'Position', [50 50 2400 1800], 'Visible', 'off');
    tiledlayout(2, 3, 'Padding', 'compact', 'TileSpacing', 'compact');

    % For each cluster, plot the five largest absolute full-year correlations.
    uniqueLevels = unique(withinClust.level);
    for li = 1:min(length(uniqueLevels), 6)
        nexttile;
        level = uniqueLevels(li);
        lvlData = withinClust(withinClust.level == level, :);
        if height(lvlData) == 0
            title(sprintf('%s: no pairs', level));
            continue;
        end

        if any(strcmp(lvlData.Properties.VariableNames, 'sales_corr_全年'))
            [~, sortIdx] = sort(abs(lvlData.('sales_corr_全年')), 'descend');
            top = lvlData(sortIdx(1:min(5, height(lvlData))), :);
            rho = top.('sales_corr_全年');
            lower = top.('sales_ci_lower_全年');
            upper = top.('sales_ci_upper_全年');
            lower(~isfinite(lower)) = rho(~isfinite(lower));
            upper(~isfinite(upper)) = rho(~isfinite(upper));
            yPos = (1:height(top))';
            errorbar(rho, yPos, rho-lower, upper-rho, 'horizontal', 'o', ...
                'Color', clusterColors(li,:), 'MarkerFaceColor', 'white', ...
                'LineWidth', 1.6, 'MarkerSize', 7);
            pairLabels = strings(height(top), 1);
            for pi = 1:height(top)
                src = normalizeCode(top.source(pi));
                tgt = normalizeCode(top.target(pi));
                srcName = activity.sku_name(activityCodes == src);
                tgtName = activity.sku_name(activityCodes == tgt);
                if isempty(srcName), srcName = src; end
                if isempty(tgtName), tgtName = tgt; end
                pairLabels(pi) = srcName(1) + "—" + tgtName(1);
            end
            yticks(yPos); yticklabels(pairLabels); set(gca, 'YDir', 'reverse');
            xline(0, 'k--', 'LineWidth', 1);
            xlabel('Full-year Spearman correlation (95% CI)');
            title(strrep(level, 'within_cluster_', '簇'));
            xlim([-1 1]); grid on;
        else
            title(sprintf('%s: no full-year data', level));
        end
    end
    sgtitle('Representative SKU Pair Relationships by Level');
    exportFig(fig, fullfile(figureDir, 'fig_q1_representative_pairs'));
catch ME
    warning('Figure 7 failed: %s', ME.message);
end

fprintf('Generated %d figures in %s\n', figCount, figureDir);

% =======================================================================
% Helper: export figure as PNG (600 dpi) + PDF
% =======================================================================
function exportFig(fig, basePath)
    set(fig, 'Color', 'white');
    drawnow;

    % PNG 600 dpi
    print(fig, sprintf('%s.png', basePath), '-dpng', '-r600');

    % PDF vector
    print(fig, sprintf('%s.pdf', basePath), '-dpdf', '-bestfit');

    % BW preview for print
    [p, f, ~] = fileparts(basePath);
    previewDir = fullfile(p, 'print_preview');
    if ~exist(previewDir, 'dir'), mkdir(previewDir); end
    colorPreview = fullfile(previewDir, sprintf('%s_color_temp.png', f));
    bwPreview = fullfile(previewDir, sprintf('%s_bw_preview.png', f));
    print(fig, colorPreview, '-dpng', '-r150');
    rgb = imread(colorPreview);
    gray = rgb2gray(rgb);
    imwrite(gray, bwPreview);
    delete(colorPreview);
end

% =======================================================================
% Helper: blue-white-red colormap
% =======================================================================
function cmap = greenwhitepurple(n)
    if nargin < 1, n = 256; end
    green = [19 103 100] / 255;
    white = [1 1 1];
    purple = [162 162 255] / 255;

    half = floor(n / 2);
    r = [linspace(green(1), white(1), half)'; linspace(white(1), purple(1), n-half)'];
    g = [linspace(green(2), white(2), half)'; linspace(white(2), purple(2), n-half)'];
    b = [linspace(green(3), white(3), half)'; linspace(white(3), purple(3), n-half)'];
    cmap = [r g b];
end

function code = normalizeCode(value)
    if isnumeric(value)
        code = string(sprintf('%.0f', value));
    else
        code = string(value);
    end
end
