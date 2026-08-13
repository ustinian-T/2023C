%% Q2 品类级补货与定价结果图（增强视觉版）
% 数据来源：questions/q2/outputs/tables 下由 q2_model.py 生成的正式 CSV。
% 设计原则：不平滑、不插值、不修改结果；所有可见数值最多保留两位小数。
% MATLAB 版本：R2023b。

clear; close all; clc;

scriptPath = mfilename('fullpath');
codeDir = fileparts(scriptPath);
q2Dir = fileparts(codeDir);
tableDir = fullfile(q2Dir, 'outputs', 'tables');
figureDir = fullfile(q2Dir, 'outputs', 'figures');
if ~exist(figureDir, 'dir'), mkdir(figureDir); end

natureColors = [110 143 178;125 164 148;234 182 122;229 167 154;193 110 113; ...
                171 200 229;216 160 193;159 141 184;208 208 138]/255;
fontName = 'Microsoft YaHei';

strategy = readtable(fullfile(tableDir, 'q2_daily_strategy.csv'), ...
    'TextType','string','VariableNamingRule','preserve');
elasticity = readtable(fullfile(tableDir, 'q2_elasticity_estimates.csv'), ...
    'TextType','string','VariableNamingRule','preserve');
comparison = readtable(fullfile(tableDir, 'q2_model_comparison.csv'), ...
    'TextType','string','VariableNamingRule','preserve');
sensitivity = readtable(fullfile(tableDir, 'q2_sensitivity_analysis.csv'), ...
    'TextType','string','VariableNamingRule','preserve');
riskSummary = readtable(fullfile(tableDir, 'q2_weekly_risk_summary.csv'), ...
    'TextType','string','VariableNamingRule','preserve');

strategy.date = datetime(strategy.date,'InputFormat','yyyy-MM-dd');
categories = unique(strategy.category_name,'stable');
dateTicks = unique(strategy.date,'stable');
dateLabels = cellstr(string(dateTicks,'MM-dd'));
nCat = numel(categories); nDay = numel(dateTicks);

replenishment = nan(nCat,nDay);
price = nan(nCat,nDay);
for i = 1:nCat
    for j = 1:nDay
        row = strategy.category_name == categories(i) & strategy.date == dateTicks(j);
        assert(nnz(row)==1,'日—品类策略表存在缺失或重复行。');
        replenishment(i,j) = strategy.replenishment_kg(row);
        price(i,j) = strategy.price_yuan_per_kg(row);
    end
end

%% 图 1：未来一周补货与定价轨迹（保留原论文图）
fig = figure('Color','w','Position',[50 80 1500 720]);
tl = tiledlayout(fig,1,2,'TileSpacing','compact','Padding','compact');
xDay = 1:nDay;

ax1 = nexttile(tl); hold(ax1,'on');
drawRidgeSeries(ax1,xDay,replenishment,categories,dateLabels,natureColors, ...
    '日补货量（kg）','补货决策三维填充折线',fontName);

ax2 = nexttile(tl); hold(ax2,'on');
drawRidgeSeries(ax2,xDay,price,categories,dateLabels,natureColors, ...
    '建议售价（元/kg）','定价决策三维填充折线',fontName);

title(tl,'2023 年 7 月 1—7 日品类级补货与定价策略', ...
    'FontName',fontName,'FontWeight','bold','FontSize',16);
exportPaperFigure(fig,figureDir,'fig_q2_daily_replenishment_pricing');

%% 图 2：双热力图——同时读出 42 条补货与定价决策
fig = figure('Color','w','Position',[45 70 1500 760]);
blueGreenMap = [222 235 244; 151 197 202; 91 165 154; 110 143 178]/255;
redOrangeMap = [247 231 207; 235 183 126; 218 139 111; 193 110 113]/255;
repSimilarity = corr(replenishment,'Rows','pairwise');
priceSimilarity = corr(price,'Rows','pairwise');
tl = tiledlayout(fig,1,2,'TileSpacing','compact','Padding','compact');
ax1 = nexttile(tl); hold(ax1,'on');
drawTriangularMatrix(ax1,repSimilarity,dateLabels,blueGreenMap,'upper', ...
    '每日补货结构相似度',fontName);
ax2 = nexttile(tl); hold(ax2,'on');
drawTriangularMatrix(ax2,priceSimilarity,dateLabels,redOrangeMap,'lower', ...
    '每日定价结构相似度',fontName);
title(tl,'2023 年 7 月 1—7 日补货与定价策略的日期间相似性', ...
    'FontName',fontName,'FontWeight','bold','FontSize',16);
exportPaperFigure(fig,figureDir,'fig_q2_strategy_heatmaps');

if strcmp(getenv('Q2_HEATMAP_ONLY'),'1')
    fprintf('Q2 三维热力图预览已生成至：%s\n',figureDir);
    return;
end

%% 图 3：森林图——条件价格响应及识别边界
fig = figure('Color','w','Position',[100 100 1120 650]);
ax = axes(fig); hold(ax,'on');
y = (1:height(elasticity))';
raw = elasticity.elasticity_raw;
lo = elasticity.ci_lower;
hi = elasticity.ci_upper;
used = elasticity.elasticity_used;
fallback = logical(elasticity.pooled_fallback_applied);

% 识别区域底色：负响应区、零附近区和正响应区
xPatch = [-2.5 -0.5 -0.5 -2.5];
patch(ax,xPatch,[0.5 0.5 6.5 6.5],natureColors(1,:), ...
    'FaceAlpha',0.11,'EdgeColor','none','HandleVisibility','off');
patch(ax,[-0.5 0.25 0.25 -0.5],[0.5 0.5 6.5 6.5],natureColors(3,:), ...
    'FaceAlpha',0.10,'EdgeColor','none','HandleVisibility','off');
patch(ax,[0.25 1.7 1.7 0.25],[0.5 0.5 6.5 6.5],natureColors(5,:), ...
    'FaceAlpha',0.085,'EdgeColor','none','HandleVisibility','off');
addHorizontalRowBands(ax,6,[-2.5 1.7]);

for i = 1:height(elasticity)
    plot(ax,[lo(i),hi(i)],[y(i),y(i)],'-','Color',[0.62 0.62 0.62], ...
        'LineWidth',2.2,'HandleVisibility','off');
    plot(ax,[lo(i),lo(i)],[y(i)-0.08,y(i)+0.08],'-','Color',[0.62 0.62 0.62], ...
        'LineWidth',1.1,'HandleVisibility','off');
    plot(ax,[hi(i),hi(i)],[y(i)-0.08,y(i)+0.08],'-','Color',[0.62 0.62 0.62], ...
        'LineWidth',1.1,'HandleVisibility','off');
end
for i = find(fallback)'
    quiver(ax,raw(i),y(i),used(i)-raw(i),0,0,'Color',natureColors(8,:), ...
        'LineWidth',1.8,'MaxHeadSize',0.18,'HandleVisibility','off');
end
hRaw = scatter(ax,raw,y,62,'o','MarkerEdgeColor',natureColors(1,:), ...
    'MarkerFaceColor','w','LineWidth',1.6,'DisplayName','原始估计');
hUsed = scatter(ax,used,y,64,'s','MarkerEdgeColor',natureColors(5,:), ...
    'MarkerFaceColor',natureColors(5,:),'LineWidth',1.2,'DisplayName','优化采用值');
scatter(ax,used(fallback),y(fallback),150,'d','MarkerEdgeColor',natureColors(8,:), ...
    'MarkerFaceColor','none','LineWidth',1.8,'DisplayName','合并响应回退');
hZero = xline(ax,0,'--','零响应','Color',[0.25 0.25 0.25],'LineWidth',1.1, ...
    'LabelVerticalAlignment','bottom');
hZero.HandleVisibility = 'off';
for i = 1:height(elasticity)
    text(ax,max(hi(i),used(i))+0.07,y(i),sprintf('采用 %.2f',used(i)), ...
        'FontName',fontName,'FontSize',9,'VerticalAlignment','middle');
end
set(ax,'YTick',y,'YTickLabel',elasticity.category_name,'YDir','reverse');
xlabel(ax,'条件价格响应系数（对数销量 / 对数价格）');
title(ax,'条件价格响应的估计、区间与优化采用值');
legend(ax,'Location','southoutside','Orientation','horizontal','NumColumns',3);
styleAxes(ax,fontName); xlim(ax,[min(lo)-0.18,max(hi)+0.65]);
ax.Color = [0.985 0.988 0.990];
exportPaperFigure(fig,figureDir,'fig_q2_price_response_forest');

%% 图 4：哑铃图——主策略相对历史基线的收益改善
fig = figure('Color','w','Position',[120 100 1180 670]);
ax = axes(fig); hold(ax,'on');
metricNames = {'经营利润期望','服务调整利润期望','经营利润最差 10% 均值','服务调整利润最差 10% 均值'};
base = [comparison.weekly_expected_profit_yuan(1), ...
        comparison.weekly_expected_service_adjusted_profit_yuan(1), ...
        comparison.weekly_worst10pct_mean_profit_yuan(1), ...
        comparison.weekly_worst10pct_service_adjusted_profit_yuan(1)];
main = [comparison.weekly_expected_profit_yuan(2), ...
        comparison.weekly_expected_service_adjusted_profit_yuan(2), ...
        comparison.weekly_worst10pct_mean_profit_yuan(2), ...
        comparison.weekly_worst10pct_service_adjusted_profit_yuan(2)];
y = 1:numel(metricNames);
addHorizontalRowBands(ax,numel(y),[-1800 5500]);
for i = 1:numel(y)
    plot(ax,[base(i),main(i)],[y(i),y(i)],'-','Color',[0.73 0.73 0.73], ...
        'LineWidth',4,'HandleVisibility','off');
end
hBase = scatter(ax,base,y,78,'o','MarkerFaceColor','w','MarkerEdgeColor',natureColors(2,:), ...
    'LineWidth',1.8,'DisplayName','历史中位基线');
hMain = scatter(ax,main,y,86,'s','MarkerFaceColor',natureColors(1,:), ...
    'MarkerEdgeColor',natureColors(1,:),'LineWidth',1.2,'DisplayName','Q2 主策略');
xline(ax,0,'-','Color',[0.30 0.30 0.30],'LineWidth',0.9,'HandleVisibility','off');
for i = 1:numel(y)
    text(ax,base(i)-85,y(i),sprintf('%.0f',base(i)), ...
        'HorizontalAlignment','right','VerticalAlignment','middle','FontName',fontName,'FontSize',9.5);
    text(ax,main(i)+85,y(i),sprintf('%.0f',main(i)), ...
        'HorizontalAlignment','left','VerticalAlignment','middle','FontName',fontName,'FontSize',9.5);
end
delta = main-base;
text(ax,(base+main)/2,y-0.16,arrayfun(@(v)sprintf('+%.0f',v),delta,'UniformOutput',false), ...
    'HorizontalAlignment','center','FontName',fontName,'FontSize',9,'Color',[0.32 0.32 0.32]);
set(ax,'YTick',y,'YTickLabel',metricNames,'YDir','reverse');
xlabel(ax,'周收益（元）');
title(ax,'Q2 主策略相对历史中位基线的同口径收益改善');
legend(ax,[hBase hMain],'Location','southoutside','Orientation','horizontal');
styleAxes(ax,fontName); xlim(ax,[min(base)-650,max(main)+650]);
ylim(ax,[0.55,numel(y)+0.45]);
ax.Color = [0.970 0.982 0.986];
exportPaperFigure(fig,figureDir,'fig_q2_profit_dumbbell');

%% 图 5：风险—收益权衡图——解释主风险权重 0.25 的选择
fig = figure('Color','w','Position',[140 100 1000 680]);
ax = axes(fig); hold(ax,'on');
x = riskSummary.weekly_worst10pct_regularized_profit_yuan;
y = riskSummary.weekly_expected_regularized_profit_yuan;
gamma = riskSummary.risk_weight;
% 主方案十字参考线和柔和光晕，强调折中位置
mainIdx = find(abs(gamma-0.25)<1e-12,1);
xline(ax,x(mainIdx),':','Color',natureColors(5,:),'LineWidth',1.0,'HandleVisibility','off');
yline(ax,y(mainIdx),':','Color',natureColors(5,:),'LineWidth',1.0,'HandleVisibility','off');
scatter(ax,x(mainIdx),y(mainIdx),500,'o','MarkerFaceColor',natureColors(5,:), ...
    'MarkerFaceAlpha',0.10,'MarkerEdgeColor','none','HandleVisibility','off');
plot(ax,x,y,'-','Color',[0.65 0.65 0.65],'LineWidth',2.4,'HandleVisibility','off');
for i = 1:numel(x)-1
    quiver(ax,x(i),y(i),x(i+1)-x(i),y(i+1)-y(i),0,'Color',[0.58 0.58 0.58], ...
        'LineWidth',1.2,'MaxHeadSize',0.12,'HandleVisibility','off');
end
for i = 1:height(riskSummary)
    if abs(gamma(i)-0.25)<1e-12
        scatter(ax,x(i),y(i),130,'s','MarkerFaceColor',natureColors(5,:), ...
            'MarkerEdgeColor',[0.25 0.25 0.25],'LineWidth',1.2);
    else
        scatter(ax,x(i),y(i),90,'o','MarkerFaceColor','w', ...
            'MarkerEdgeColor',natureColors(1,:),'LineWidth',1.7);
    end
    text(ax,x(i)+12,y(i)+5,sprintf('风险权重 %.2f',gamma(i)), ...
        'FontName',fontName,'FontSize',10,'VerticalAlignment','bottom');
end
xlabel(ax,'最差 10% 正则化评价均值（元，越高越稳健）');
ylabel(ax,'正则化评价期望（元，越高越好）');
title(ax,'三档风险权重下的期望—下尾权衡');
styleAxes(ax,fontName);
xlim(ax,[min(x)-70,max(x)+115]); ylim(ax,[min(y)-35,max(y)+35]);
ax.Color = [0.990 0.974 0.972];
exportPaperFigure(fig,figureDir,'fig_q2_risk_return_tradeoff');

%% 图 6：四联敏感性图——分别展示两个管理参数的作用链
fig = figure('Color','w','Position',[70 70 1320 770]);
tl = tiledlayout(fig,2,2,'TileSpacing','compact','Padding','compact');
gw = sensitivity.parameter == "goodwill_cost_ratio";
gws = sortrows(sensitivity(gw,:),'value');
rw = sensitivity.parameter == "reference_penalty_weight";
rws = sortrows(sensitivity(rw,:),'value');

ax1 = nexttile(tl); hold(ax1,'on');
addAreaUnderCurve(ax1,gws.value,gws.weekly_replenishment_kg,natureColors(1,:),0.13);
plot(ax1,gws.value,gws.weekly_replenishment_kg,'-o','Color',natureColors(1,:), ...
    'LineWidth',2,'MarkerSize',7,'MarkerFaceColor','w');
addPointLabels(ax1,gws.value,gws.weekly_replenishment_kg,'%.0f',fontName);
xlabel(ax1,'商誉成本系数'); ylabel(ax1,'周补货量（kg）');
title(ax1,'服务偏好增强 → 补货增加'); styleAxes(ax1,fontName); xticks(ax1,gws.value);
ax1.Color = [0.962 0.975 0.986];
xlim(ax1,[-0.012 0.212]); ylim(ax1,paddedLimits(gws.weekly_replenishment_kg,0.10));

ax2 = nexttile(tl); hold(ax2,'on');
addAreaUnderCurve(ax2,gws.value,100*gws.mean_stockout_probability,natureColors(5,:),0.12);
plot(ax2,gws.value,100*gws.mean_stockout_probability,'--s','Color',natureColors(5,:), ...
    'LineWidth',2,'MarkerSize',7,'MarkerFaceColor','w');
addPointLabels(ax2,gws.value,100*gws.mean_stockout_probability,'%.1f%%',fontName);
xlabel(ax2,'商誉成本系数'); ylabel(ax2,'平均场景缺货概率（%）');
title(ax2,'服务偏好增强 → 场景缺货下降'); styleAxes(ax2,fontName); xticks(ax2,gws.value);
ax2.Color = [0.992 0.970 0.968];
xlim(ax2,[-0.012 0.212]); ylim(ax2,paddedLimits(100*gws.mean_stockout_probability,0.12));

ax3 = nexttile(tl); hold(ax3,'on');
addAreaUnderCurve(ax3,rws.value,rws.mean_markup_rate,natureColors(2,:),0.13);
plot(ax3,rws.value,rws.mean_markup_rate,'-^','Color',natureColors(2,:), ...
    'LineWidth',2,'MarkerSize',7,'MarkerFaceColor','w');
addPointLabels(ax3,rws.value,rws.mean_markup_rate,'%.2f',fontName);
xlabel(ax3,'参考加价正则权重'); ylabel(ax3,'平均加价率');
title(ax3,'正则增强 → 平均加价率下降'); styleAxes(ax3,fontName); xticks(ax3,rws.value);
ax3.Color = [0.965 0.982 0.973];
xlim(ax3,[-28 528]); ylim(ax3,paddedLimits(rws.mean_markup_rate,0.14));

ax4 = nexttile(tl); hold(ax4,'on');
addAreaUnderCurve(ax4,rws.value,rws.markups_at_upper_bound,natureColors(4,:),0.13);
plot(ax4,rws.value,rws.markups_at_upper_bound,'-.d','Color',natureColors(4,:), ...
    'LineWidth',2,'MarkerSize',7,'MarkerFaceColor','w');
addPointLabels(ax4,rws.value,rws.markups_at_upper_bound,'%.0f',fontName);
xlabel(ax4,'参考加价正则权重'); ylabel(ax4,'触及加价上界的决策数（条）');
title(ax4,'正则增强 → 极端加价减少'); styleAxes(ax4,fontName); xticks(ax4,rws.value);
ax4.Color = [0.994 0.977 0.955];
xlim(ax4,[-28 528]); ylim(ax4,paddedLimits(rws.markups_at_upper_bound,0.16));

title(tl,'Q2 策略对关键管理参数的敏感性', ...
    'FontName',fontName,'FontWeight','bold','FontSize',15);
exportPaperFigure(fig,figureDir,'fig_q2_management_sensitivity');

fprintf('Q2 增强版图表已生成至：%s\n',figureDir);

function drawRidgeSeries(ax,x,data,categories,dateLabels,colors,zLabel,panelTitle,fontName)
    nSeries = size(data,1);
    for i = nSeries:-1:1
        y = i*ones(size(x));
        patch(ax,[x fliplr(x)],[y fliplr(y)], ...
            [data(i,:) zeros(size(x))],colors(i,:), ...
            'FaceAlpha',0.72,'EdgeColor','none','HandleVisibility','off');
        plot3(ax,x,y,data(i,:),'-','Color',0.72*colors(i,:), ...
            'LineWidth',2.1,'HandleVisibility','off');
        scatter3(ax,x,y,data(i,:),28,'o','MarkerFaceColor',colors(i,:), ...
            'MarkerEdgeColor','w','LineWidth',0.7,'HandleVisibility','off');
        plot3(ax,[x(1) x(end)],[i i],[0 0],'-','Color',[0.82 0.82 0.82], ...
            'LineWidth',0.7,'HandleVisibility','off');
    end
    xlim(ax,[min(x) max(x)]); ylim(ax,[0.65 nSeries+0.35]);
    zlim(ax,[0 max(data(:))*1.10]);
    ax.XTick = x; ax.XTickLabel = dateLabels;
    ax.YTick = 1:nSeries; ax.YTickLabel = categories;
    xlabel(ax,'日期'); ylabel(ax,'品类'); zlabel(ax,zLabel);
    title(ax,panelTitle,'FontWeight','bold');
    view(ax,[-48 25]); grid(ax,'on'); box(ax,'on');
    ax.GridAlpha = 0.14; ax.MinorGridAlpha = 0.07;
    ax.FontName = fontName; ax.FontSize = 10; ax.LineWidth = 0.8;
    ax.Projection = 'perspective';
    set(ax,'Color',[0.985 0.985 0.985]);
end

function drawBlockHeatmap(ax,data,dateLabels,categories,palette,zLabel,panelTitle,fontName)
    h = bar3(ax,data,0.78);
    for k = 1:numel(h)
        z = h(k).ZData;
        h(k).CData = z;
        h(k).FaceColor = 'interp';
        h(k).EdgeColor = [0.40 0.43 0.44];
        h(k).LineWidth = 0.42;
        h(k).FaceAlpha = 0.96;
    end
    colormap(ax,multiAnchorMap(palette,256));
    clim(ax,[min(data(:)) max(data(:))]);
    cb = colorbar(ax,'Location','eastoutside');
    cb.Label.String = zLabel; cb.FontName = fontName;
    ax.XTick = 1:numel(dateLabels); ax.XTickLabel = dateLabels;
    ax.YTick = 1:numel(categories); ax.YTickLabel = categories;
    xlabel(ax,'日期'); ylabel(ax,'品类'); zlabel(ax,zLabel);
    title(ax,panelTitle,'FontWeight','bold');
    view(ax,[-47 28]); grid(ax,'on'); box(ax,'on');
    ax.GridAlpha = 0.16; ax.FontName = fontName; ax.FontSize = 9.5;
    ax.LineWidth = 0.8; ax.Projection = 'perspective';
    zlim(ax,[0 max(data(:))*1.08]);
    set(ax,'Color',[0.985 0.985 0.985]);
end

function drawTriangularMatrix(ax,data,labels,palette,triangleSide,panelTitle,fontName)
    n = size(data,1);
    cmap = multiAnchorMap(palette,256);
    dataMin = min(data(:)); dataMax = max(data(:));
    if abs(dataMax-dataMin)<eps, dataMin = dataMin-0.01; end
    for r = 1:n
        for c = 1:n
            showCell = (strcmp(triangleSide,'upper') && c>=r) || ...
                       (strcmp(triangleSide,'lower') && c<=r);
            if ~showCell, continue; end
            t = (data(r,c)-dataMin)/max(dataMax-dataMin,eps);
            faceColor = sampleMap(cmap,t);
            rectangle(ax,'Position',[c-0.5 r-0.5 1 1], ...
                'FaceColor',faceColor,'EdgeColor',[0.28 0.30 0.31],'LineWidth',0.65);
            text(ax,c,r,sprintf('%.2f',data(r,c)), ...
                'HorizontalAlignment','center','VerticalAlignment','middle', ...
                'FontName',fontName,'FontSize',8.5,'FontWeight','bold', ...
                'Color',contrastColor(faceColor));
        end
    end
    axis(ax,'equal'); xlim(ax,[0.5 n+0.5]); ylim(ax,[0.5 n+0.5]);
    set(ax,'YDir','reverse','Color','w');
    ax.XTick = 1:n; ax.XTickLabel = labels;
    ax.YTick = 1:n; ax.YTickLabel = labels;
    ax.TickLength = [0 0]; ax.FontName = fontName; ax.FontSize = 10;
    if strcmp(triangleSide,'upper'), ax.XAxisLocation = 'top'; end
    title(ax,panelTitle,'FontWeight','bold','FontSize',13);
    box(ax,'off'); ax.XColor = [0.20 0.20 0.20]; ax.YColor = [0.20 0.20 0.20];
    colormap(ax,cmap); clim(ax,[dataMin dataMax]);
    cb = colorbar(ax,'southoutside');
    cb.Label.String = 'Pearson 相关系数'; cb.FontName = fontName;
end

function drawSplitTriangleHeatmap(ax,replenishment,price,dateLabels,categories,repMap,priceMap,fontName)
    nRow = size(replenishment,1); nCol = size(replenishment,2);
    repMin = min(replenishment(:)); repMax = max(replenishment(:));
    priceMin = min(price(:)); priceMax = max(price(:));
    repCmap = multiAnchorMap(repMap,256);
    priceCmap = multiAnchorMap(priceMap,256);
    for r = 1:nRow
        for c = 1:nCol
            repT = (replenishment(r,c)-repMin)/max(repMax-repMin,eps);
            priceT = (price(r,c)-priceMin)/max(priceMax-priceMin,eps);
            repColor = sampleMap(repCmap,repT);
            priceColor = sampleMap(priceCmap,priceT);
            patch(ax,[c-0.5 c-0.5 c+0.5],[r-0.5 r+0.5 r+0.5],repColor,'EdgeColor','none');
            patch(ax,[c-0.5 c+0.5 c+0.5],[r-0.5 r-0.5 r+0.5],priceColor,'EdgeColor','none');
            plot(ax,[c-0.5 c+0.5],[r-0.5 r+0.5],'-','Color',[0.92 0.92 0.92], ...
                'LineWidth',0.8,'HandleVisibility','off');
            text(ax,c-0.18,r+0.18,sprintf('%.1f',replenishment(r,c)), ...
                'HorizontalAlignment','center','FontName',fontName,'FontSize',7.5, ...
                'FontWeight','bold','Color',contrastColor(repColor));
            text(ax,c+0.18,r-0.18,sprintf('%.2f',price(r,c)), ...
                'HorizontalAlignment','center','FontName',fontName,'FontSize',7.5, ...
                'FontWeight','bold','Color',contrastColor(priceColor));
        end
    end
    for c = 0.5:1:(nCol+0.5)
        plot(ax,[c c],[0.5 nRow+0.5],'-','Color',[0.46 0.48 0.49],'LineWidth',0.55);
    end
    for r = 0.5:1:(nRow+0.5)
        plot(ax,[0.5 nCol+0.5],[r r],'-','Color',[0.46 0.48 0.49],'LineWidth',0.55);
    end
    axis(ax,'equal'); axis(ax,'tight'); set(ax,'YDir','reverse');
    ax.XTick = 1:nCol; ax.XTickLabel = dateLabels;
    ax.YTick = 1:nRow; ax.YTickLabel = categories;
    ax.TickLength = [0 0]; ax.FontName = fontName; ax.FontSize = 10.5;
    xlabel(ax,'日期'); ylabel(ax,'品类'); box(ax,'on'); ax.LineWidth = 0.9;
end

function drawTriangleColorScales(fig,replenishment,price,repMap,priceMap,fontName)
    ax1 = axes(fig,'Position',[0.845 0.54 0.025 0.28]);
    imagesc(ax1,1,linspace(min(replenishment(:)),max(replenishment(:)),256),linspace(0,1,256)');
    colormap(ax1,multiAnchorMap(repMap,256)); set(ax1,'YDir','normal','XTick',[],'YAxisLocation','right');
    ylabel(ax1,'补货量（kg）','FontName',fontName); ax1.FontName = fontName; box(ax1,'on');
    ax2 = axes(fig,'Position',[0.845 0.18 0.025 0.28]);
    imagesc(ax2,1,linspace(min(price(:)),max(price(:)),256),linspace(0,1,256)');
    colormap(ax2,multiAnchorMap(priceMap,256)); set(ax2,'YDir','normal','XTick',[],'YAxisLocation','right');
    ylabel(ax2,'建议售价（元/kg）','FontName',fontName); ax2.FontName = fontName; box(ax2,'on');
    annotation(fig,'textbox',[0.815 0.465 0.16 0.065], ...
        'String',{'左下三角：补货量','右上三角：建议售价'}, ...
        'FontName',fontName,'FontSize',9.5,'HorizontalAlignment','center', ...
        'VerticalAlignment','middle','EdgeColor',[0.72 0.72 0.72], ...
        'BackgroundColor',[0.985 0.985 0.985],'FitBoxToText','off');
end

function color = sampleMap(cmap,t)
    idx = 1 + round(min(max(t,0),1)*(size(cmap,1)-1));
    color = cmap(idx,:);
end

function color = contrastColor(rgb)
    luminance = 0.2126*rgb(1)+0.7152*rgb(2)+0.0722*rgb(3);
    if luminance < 0.59, color = [1 1 1]; else, color = [0.12 0.12 0.12]; end
end

function cmap = multiAnchorMap(palette,n)
    anchors = linspace(0,1,size(palette,1));
    query = linspace(0,1,n);
    cmap = interp1(anchors,palette,query,'pchip');
    cmap = min(max(cmap,0),1);
end

function formatHeatmap(ax,dateLabels,categories,panelTitle,fontName)
    ax.XTick = 1:numel(dateLabels); ax.XTickLabel = dateLabels;
    ax.YTick = 1:numel(categories); ax.YTickLabel = categories;
    ax.TickLength = [0 0]; ax.FontName = fontName; ax.FontSize = 10.5;
    xlabel(ax,'日期'); ylabel(ax,'品类'); title(ax,panelTitle);
    ax.XGrid = 'off'; ax.YGrid = 'off'; ax.LineWidth = 0.8; box(ax,'on');
    hold(ax,'on');
    for x = 1.5:(numel(dateLabels)-0.5)
        plot(ax,[x x],[0.5 numel(categories)+0.5],'-','Color',[0.96 0.96 0.96], ...
            'LineWidth',0.7,'HandleVisibility','off');
    end
    for y = 1.5:(numel(categories)-0.5)
        plot(ax,[0.5 numel(dateLabels)+0.5],[y y],'-','Color',[0.96 0.96 0.96], ...
            'LineWidth',0.7,'HandleVisibility','off');
    end
end

function addCellLabels(ax,data,fmt)
    clim = caxis(ax); split = mean(clim);
    for r = 1:size(data,1)
        for c = 1:size(data,2)
            color = [0.12 0.12 0.12];
            if data(r,c) > split, color = [1 1 1]; end
            text(ax,c,r,sprintf(fmt,data(r,c)),'HorizontalAlignment','center', ...
                'VerticalAlignment','middle','FontSize',8.5,'FontWeight','bold','Color',color);
        end
    end
end

function cmap = sequentialMap(lowColor,highColor,n)
    t = linspace(0,1,n)';
    low = 0.92 + 0.08*lowColor;
    cmap = low.*(1-t) + highColor.*t;
end

function addPointLabels(ax,x,y,fmt,fontName)
    yr = max(y)-min(y); if yr==0, yr=1; end
    for i = 1:numel(x)
        text(ax,x(i),y(i)+0.035*yr,sprintf(fmt,y(i)), ...
            'HorizontalAlignment','center','VerticalAlignment','bottom', ...
            'FontName',fontName,'FontSize',9);
    end
end

function lim = paddedLimits(y,fraction)
    lo = min(y); hi = max(y); span = hi-lo;
    if span==0, span=max(abs(lo),1); end
    lim = [lo-fraction*span,hi+fraction*span];
end

function styleAxes(ax,fontName)
    grid(ax,'on'); box(ax,'on');
    ax.GridAlpha = 0.14; ax.MinorGridAlpha = 0.08; ax.LineWidth = 0.8;
    ax.FontName = fontName; ax.FontSize = 10.5;
    ax.Layer = 'top';
end

function styleDayAxes(ax,xDay,dateLabels,fontName)
    styleAxes(ax,fontName);
    ax.XTick = xDay;
    ax.XTickLabel = dateLabels;
    xlim(ax,[0.85 max(xDay)+0.15]);
end

function addAlternatingBands(ax,x,yLim,color)
    for k = 1:numel(x)
        if mod(k,2)==0
            patch(ax,[x(k)-0.5 x(k)+0.5 x(k)+0.5 x(k)-0.5], ...
                [yLim(1) yLim(1) yLim(2) yLim(2)],color, ...
                'FaceAlpha',0.035,'EdgeColor','none','HandleVisibility','off');
        end
    end
end

function addCategoryStrip(ax,nCat,colors)
    hold(ax,'on');
    for i = 1:nCat
        rectangle(ax,'Position',[0.50 i-0.48 0.10 0.96], ...
            'FaceColor',colors(i,:),'EdgeColor','none','Clipping','on');
    end
end

function addHorizontalRowBands(ax,nRows,xLim)
    for i = 1:nRows
        if mod(i,2)==0
            patch(ax,[xLim(1) xLim(2) xLim(2) xLim(1)], ...
                [i-0.5 i-0.5 i+0.5 i+0.5],[0.5 0.5 0.5], ...
                'FaceAlpha',0.035,'EdgeColor','none','HandleVisibility','off');
        end
    end
end

function addAreaUnderCurve(ax,x,y,color,alphaValue)
    base = min(y)-0.08*max(max(y)-min(y),1);
    patch(ax,[x' fliplr(x')],[y' base*ones(1,numel(y))],color, ...
        'FaceAlpha',alphaValue,'EdgeColor','none','HandleVisibility','off');
end

function exportPaperFigure(fig,outDir,stem)
    pdfPath = fullfile(outDir,[stem '.pdf']);
    pngPath = fullfile(outDir,[stem '.png']);
    exportgraphics(fig,pdfPath,'ContentType','vector','BackgroundColor','white');
    exportgraphics(fig,pngPath,'Resolution',600,'BackgroundColor','white');
end
