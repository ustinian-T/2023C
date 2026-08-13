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
fig = figure('Color','w','Position',[80 80 1320 780]);
tl = tiledlayout(fig,2,1,'TileSpacing','compact','Padding','compact');
lineStyles = {'-','--',':','-.','-','--'};
markers = {'o','s','^','d','v','>'};

ax1 = nexttile(tl); hold(ax1,'on');
for i = 1:nCat
    plot(ax1,dateTicks,replenishment(i,:), ...
        'Color',natureColors(i,:),'LineStyle',lineStyles{i}, ...
        'Marker',markers{i},'LineWidth',1.9,'MarkerSize',6, ...
        'MarkerFaceColor','w','DisplayName',categories(i));
end
ylabel(ax1,'日补货量（kg）'); title(ax1,'各品类日补货量');
legend(ax1,'Location','eastoutside','NumColumns',1);
styleDateAxes(ax1,dateTicks,dateLabels,fontName);

ax2 = nexttile(tl); hold(ax2,'on');
for i = 1:nCat
    plot(ax2,dateTicks,price(i,:), ...
        'Color',natureColors(i,:),'LineStyle',lineStyles{i}, ...
        'Marker',markers{i},'LineWidth',1.9,'MarkerSize',6, ...
        'MarkerFaceColor','w','DisplayName',categories(i));
end
ylabel(ax2,'建议售价（元/kg）'); xlabel(ax2,'日期');
title(ax2,'成本加成定价策略');
styleDateAxes(ax2,dateTicks,dateLabels,fontName);
title(tl,'2023 年 7 月 1—7 日品类级补货与定价策略', ...
    'FontName',fontName,'FontWeight','bold','FontSize',15);
exportPaperFigure(fig,figureDir,'fig_q2_daily_replenishment_pricing');

%% 图 2：双热力图——同时读出 42 条补货与定价决策
fig = figure('Color','w','Position',[80 80 1320 720]);
tl = tiledlayout(fig,1,2,'TileSpacing','compact','Padding','compact');

ax1 = nexttile(tl); imagesc(ax1,replenishment); axis(ax1,'tight');
colormap(ax1,sequentialMap(natureColors(6,:),natureColors(1,:),256));
cb1 = colorbar(ax1); cb1.Label.String = '补货量（kg）';
formatHeatmap(ax1,dateLabels,categories,'日补货量（kg）',fontName);
addCellLabels(ax1,replenishment,'%.1f');

ax2 = nexttile(tl); imagesc(ax2,price); axis(ax2,'tight');
colormap(ax2,sequentialMap(natureColors(3,:),natureColors(5,:),256));
cb2 = colorbar(ax2); cb2.Label.String = '建议售价（元/kg）';
formatHeatmap(ax2,dateLabels,categories,'建议售价（元/kg）',fontName);
addCellLabels(ax2,price,'%.2f');

title(tl,'2023 年 7 月 1—7 日品类级补货与定价决策矩阵', ...
    'FontName',fontName,'FontWeight','bold','FontSize',15);
exportPaperFigure(fig,figureDir,'fig_q2_strategy_heatmaps');

%% 图 3：森林图——条件价格响应及识别边界
fig = figure('Color','w','Position',[100 100 1120 650]);
ax = axes(fig); hold(ax,'on');
y = (1:height(elasticity))';
raw = elasticity.elasticity_raw;
lo = elasticity.ci_lower;
hi = elasticity.ci_upper;
used = elasticity.elasticity_used;
fallback = logical(elasticity.pooled_fallback_applied);

for i = 1:height(elasticity)
    plot(ax,[lo(i),hi(i)],[y(i),y(i)],'-','Color',[0.62 0.62 0.62], ...
        'LineWidth',2.2,'HandleVisibility','off');
    plot(ax,[lo(i),lo(i)],[y(i)-0.08,y(i)+0.08],'-','Color',[0.62 0.62 0.62], ...
        'LineWidth',1.1,'HandleVisibility','off');
    plot(ax,[hi(i),hi(i)],[y(i)-0.08,y(i)+0.08],'-','Color',[0.62 0.62 0.62], ...
        'LineWidth',1.1,'HandleVisibility','off');
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
set(ax,'YTick',y,'YTickLabel',metricNames,'YDir','reverse');
xlabel(ax,'周收益（元）');
title(ax,'Q2 主策略相对历史中位基线的同口径收益改善');
legend(ax,[hBase hMain],'Location','southoutside','Orientation','horizontal');
styleAxes(ax,fontName); xlim(ax,[min(base)-650,max(main)+650]);
ylim(ax,[0.55,numel(y)+0.45]);
exportPaperFigure(fig,figureDir,'fig_q2_profit_dumbbell');

%% 图 5：风险—收益权衡图——解释主风险权重 0.25 的选择
fig = figure('Color','w','Position',[140 100 1000 680]);
ax = axes(fig); hold(ax,'on');
x = riskSummary.weekly_worst10pct_regularized_profit_yuan;
y = riskSummary.weekly_expected_regularized_profit_yuan;
gamma = riskSummary.risk_weight;
plot(ax,x,y,'-','Color',[0.65 0.65 0.65],'LineWidth',2.0,'HandleVisibility','off');
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
exportPaperFigure(fig,figureDir,'fig_q2_risk_return_tradeoff');

%% 图 6：四联敏感性图——分别展示两个管理参数的作用链
fig = figure('Color','w','Position',[70 70 1320 770]);
tl = tiledlayout(fig,2,2,'TileSpacing','compact','Padding','compact');
gw = sensitivity.parameter == "goodwill_cost_ratio";
gws = sortrows(sensitivity(gw,:),'value');
rw = sensitivity.parameter == "reference_penalty_weight";
rws = sortrows(sensitivity(rw,:),'value');

ax1 = nexttile(tl); hold(ax1,'on');
plot(ax1,gws.value,gws.weekly_replenishment_kg,'-o','Color',natureColors(1,:), ...
    'LineWidth',2,'MarkerSize',7,'MarkerFaceColor','w');
addPointLabels(ax1,gws.value,gws.weekly_replenishment_kg,'%.0f',fontName);
xlabel(ax1,'商誉成本系数'); ylabel(ax1,'周补货量（kg）');
title(ax1,'服务偏好增强 → 补货增加'); styleAxes(ax1,fontName); xticks(ax1,gws.value);
xlim(ax1,[-0.012 0.212]); ylim(ax1,paddedLimits(gws.weekly_replenishment_kg,0.10));

ax2 = nexttile(tl); hold(ax2,'on');
plot(ax2,gws.value,100*gws.mean_stockout_probability,'--s','Color',natureColors(5,:), ...
    'LineWidth',2,'MarkerSize',7,'MarkerFaceColor','w');
addPointLabels(ax2,gws.value,100*gws.mean_stockout_probability,'%.1f%%',fontName);
xlabel(ax2,'商誉成本系数'); ylabel(ax2,'平均场景缺货概率（%）');
title(ax2,'服务偏好增强 → 场景缺货下降'); styleAxes(ax2,fontName); xticks(ax2,gws.value);
xlim(ax2,[-0.012 0.212]); ylim(ax2,paddedLimits(100*gws.mean_stockout_probability,0.12));

ax3 = nexttile(tl); hold(ax3,'on');
plot(ax3,rws.value,rws.mean_markup_rate,'-^','Color',natureColors(2,:), ...
    'LineWidth',2,'MarkerSize',7,'MarkerFaceColor','w');
addPointLabels(ax3,rws.value,rws.mean_markup_rate,'%.2f',fontName);
xlabel(ax3,'参考加价正则权重'); ylabel(ax3,'平均加价率');
title(ax3,'正则增强 → 平均加价率下降'); styleAxes(ax3,fontName); xticks(ax3,rws.value);
xlim(ax3,[-28 528]); ylim(ax3,paddedLimits(rws.mean_markup_rate,0.14));

ax4 = nexttile(tl); hold(ax4,'on');
plot(ax4,rws.value,rws.markups_at_upper_bound,'-.d','Color',natureColors(4,:), ...
    'LineWidth',2,'MarkerSize',7,'MarkerFaceColor','w');
addPointLabels(ax4,rws.value,rws.markups_at_upper_bound,'%.0f',fontName);
xlabel(ax4,'参考加价正则权重'); ylabel(ax4,'触及加价上界的决策数（条）');
title(ax4,'正则增强 → 极端加价减少'); styleAxes(ax4,fontName); xticks(ax4,rws.value);
xlim(ax4,[-28 528]); ylim(ax4,paddedLimits(rws.markups_at_upper_bound,0.16));

title(tl,'Q2 策略对关键管理参数的敏感性', ...
    'FontName',fontName,'FontWeight','bold','FontSize',15);
exportPaperFigure(fig,figureDir,'fig_q2_management_sensitivity');

fprintf('Q2 增强版图表已生成至：%s\n',figureDir);

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

function styleDateAxes(ax,dateTicks,dateLabels,fontName)
    styleAxes(ax,fontName);
    ax.XTick = dateTicks;
    ax.XTickLabel = dateLabels;
end

function exportPaperFigure(fig,outDir,stem)
    pdfPath = fullfile(outDir,[stem '.pdf']);
    pngPath = fullfile(outDir,[stem '.png']);
    exportgraphics(fig,pdfPath,'ContentType','vector','BackgroundColor','white');
    exportgraphics(fig,pngPath,'Resolution',600,'BackgroundColor','white');
end
