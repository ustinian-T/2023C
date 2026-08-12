%% Q2 品类级补货与定价结果图
% 数据来源：questions/q2/outputs/tables 下由 q2_model.py 生成的 CSV。
% 本脚本不平滑、不插值、不修改模型结果，仅做论文级可视化。

clear; close all; clc;

scriptPath = mfilename('fullpath');
codeDir = fileparts(scriptPath);
q2Dir = fileparts(codeDir);
tableDir = fullfile(q2Dir, 'outputs', 'tables');
figureDir = fullfile(q2Dir, 'outputs', 'figures');
if ~exist(figureDir, 'dir')
    mkdir(figureDir);
end

natureColors = [110 143 178;125 164 148;234 182 122;229 167 154;193 110 113; ...
                171 200 229;216 160 193;159 141 184;208 208 138]/255;
lineStyles = {'-','--',':','-.','-','--'};
markers = {'o','s','^','d','v','>'};

strategy = readtable(fullfile(tableDir, 'q2_daily_strategy.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve');
elasticity = readtable(fullfile(tableDir, 'q2_elasticity_estimates.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve');
comparison = readtable(fullfile(tableDir, 'q2_model_comparison.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve');
sensitivity = readtable(fullfile(tableDir, 'q2_sensitivity_analysis.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve');

strategy.date = datetime(strategy.date, 'InputFormat', 'yyyy-MM-dd');
categories = unique(strategy.category_name, 'stable');
dateTicks = unique(strategy.date, 'stable');

%% 图 1：未来一周补货与定价策略
fig = figure('Color','w','Position',[100 100 1260 760]);
tiledlayout(2,1,'TileSpacing','compact','Padding','compact');

ax1 = nexttile; hold(ax1,'on');
for i = 1:numel(categories)
    rows = strategy.category_name == categories(i);
    plot(strategy.date(rows), strategy.replenishment_kg(rows), ...
        'Color',natureColors(i,:),'LineStyle',lineStyles{i}, ...
        'Marker',markers{i},'LineWidth',1.7,'MarkerSize',6, ...
        'MarkerFaceColor','w','DisplayName',categories(i));
end
ylabel('日补货量（kg）');
title('各品类日补货总量');
legend('Location','eastoutside','NumColumns',1);
styleAxes(ax1,dateTicks);

ax2 = nexttile; hold(ax2,'on');
for i = 1:numel(categories)
    rows = strategy.category_name == categories(i);
    plot(strategy.date(rows), strategy.price_yuan_per_kg(rows), ...
        'Color',natureColors(i,:),'LineStyle',lineStyles{i}, ...
        'Marker',markers{i},'LineWidth',1.7,'MarkerSize',6, ...
        'MarkerFaceColor','w','DisplayName',categories(i));
end
ylabel('建议售价（元/kg）'); xlabel('日期');
title('成本加成定价策略');
styleAxes(ax2,dateTicks);
sgtitle('2023 年 7 月 1—7 日品类级补货与定价策略','FontWeight','bold');
exportPaperFigure(fig, figureDir, 'fig_q2_daily_replenishment_pricing');

%% 图 2：价格响应估计及识别边界
fig = figure('Color','w','Position',[120 120 1050 620]);
ax = axes(fig); hold(ax,'on');
y = 1:height(elasticity);
raw = elasticity.elasticity_raw;
lo = elasticity.ci_lower;
hi = elasticity.ci_upper;
used = elasticity.elasticity_used;

for i = 1:height(elasticity)
    plot([lo(i),hi(i)],[y(i),y(i)],'-','Color',[0.55 0.55 0.55], ...
        'LineWidth',1.8,'HandleVisibility','off');
end
h1 = scatter(raw,y,54,'o','MarkerEdgeColor',natureColors(1,:), ...
    'MarkerFaceColor','w','LineWidth',1.5,'DisplayName','原始条件响应');
h2 = scatter(used,y,60,'s','MarkerEdgeColor',natureColors(5,:), ...
    'MarkerFaceColor',natureColors(5,:),'LineWidth',1.2,'DisplayName','优化采用值');
xline(0,'--','零响应','Color',[0.25 0.25 0.25],'LineWidth',1.1, ...
    'LabelVerticalAlignment','bottom');
set(ax,'YTick',y,'YTickLabel',elasticity.category_name,'YDir','reverse');
xlabel('价格响应系数（对数销量 / 对数价格）');
title('品类价格响应估计与 95% 置信区间');
legend([h1 h2],'Location','southoutside','Orientation','horizontal');
grid on; box on; ax.GridAlpha=0.15; ax.LineWidth=0.8;
ax.FontName='Microsoft YaHei'; ax.FontSize=11;
annotation(fig,'textbox',[0.16 0.01 0.78 0.08], ...
    'String','注：茄类、辣椒类原始估计非负，优化采用全品类合并响应回退；该结果不解释为因果弹性。', ...
    'EdgeColor','none','HorizontalAlignment','center','FontName','Microsoft YaHei','FontSize',10);
exportPaperFigure(fig, figureDir, 'fig_q2_elasticity_identification');

%% 图 3：基线与主策略的收益对比
fig = figure('Color','w','Position',[140 140 1120 660]);
ax = axes(fig);
metrics = [comparison.weekly_expected_profit_yuan, ...
           comparison.weekly_expected_service_adjusted_profit_yuan, ...
           comparison.weekly_worst10pct_mean_profit_yuan, ...
           comparison.weekly_worst10pct_service_adjusted_profit_yuan];
b = bar(metrics','grouped','LineWidth',0.8);
b(1).FaceColor = natureColors(2,:); b(1).EdgeColor = [0.25 0.25 0.25];
b(2).FaceColor = natureColors(1,:); b(2).EdgeColor = [0.25 0.25 0.25];
b(1).LineStyle = '--'; b(2).LineStyle = '-';
yline(0,'-','Color',[0.30 0.30 0.30],'LineWidth',0.9,'HandleVisibility','off');
set(ax,'XTickLabel',{'经营利润期望','服务调整利润期望','经营利润最差 10% 均值','服务调整利润最差 10% 均值'});
ylabel('周收益（元）');
title('历史中位策略与 Q2 主策略的同口径收益对比');
legend({'历史中位基线','Q2 主策略'},'Location','northwest');
grid on; box on; ax.GridAlpha=0.15; ax.LineWidth=0.8;
ax.FontName='Microsoft YaHei'; ax.FontSize=11;
ylim(ax,[-2000 5400]);
xtickangle(12);
for k = 1:numel(b)
    x = b(k).XEndPoints; yv = b(k).YEndPoints;
    for j = 1:numel(x)
        va = 'bottom'; if yv(j) < 0, va = 'top'; end
        text(x(j),yv(j),sprintf('%.0f',yv(j)), ...
            'HorizontalAlignment','center','VerticalAlignment',va, ...
            'FontName','Microsoft YaHei','FontSize',9);
    end
end
exportPaperFigure(fig, figureDir, 'fig_q2_baseline_profit_comparison');

%% 图 4：关键管理参数敏感性
fig = figure('Color','w','Position',[160 160 1250 520]);
tiledlayout(1,2,'TileSpacing','compact','Padding','compact');

gw = sensitivity.parameter == "goodwill_cost_ratio";
gws = sensitivity(gw,:);
ax1 = nexttile; hold(ax1,'on');
yyaxis(ax1,'left');
p1 = plot(gws.value,gws.weekly_replenishment_kg,'-o', ...
    'Color',natureColors(1,:),'LineWidth',1.8,'MarkerSize',6,'MarkerFaceColor','w');
ylabel('周补货量（kg）');
yyaxis(ax1,'right');
p2 = plot(gws.value,100*gws.mean_stockout_probability,'--s', ...
    'Color',natureColors(5,:),'LineWidth',1.8,'MarkerSize',6,'MarkerFaceColor','w');
ylabel('平均缺货概率（%）'); xlabel('商誉成本系数');
title('商誉成本提高推动补货并降低缺货');
legend([p1 p2],{'周补货量','平均缺货概率'},'Location','best');
styleNumericAxes(ax1);
ax1.YAxis(1).Color = natureColors(1,:);
ax1.YAxis(2).Color = natureColors(5,:);
xticks(ax1,gws.value);

rw = sensitivity.parameter == "reference_penalty_weight";
rws = sensitivity(rw,:);
ax2 = nexttile; hold(ax2,'on');
yyaxis(ax2,'left');
p3 = plot(rws.value,rws.mean_markup_rate,'-^', ...
    'Color',natureColors(2,:),'LineWidth',1.8,'MarkerSize',6,'MarkerFaceColor','w');
ylabel('平均加价率');
yyaxis(ax2,'right');
p4 = plot(rws.value,rws.markups_at_upper_bound,'-.d', ...
    'Color',natureColors(4,:),'LineWidth',1.8,'MarkerSize',6,'MarkerFaceColor','w');
ylabel('触及加价上界的决策数（条）'); xlabel('参考加价正则权重');
title('参考正则抑制极端加价');
legend([p3 p4],{'平均加价率','加价触顶数'},'Location','best');
styleNumericAxes(ax2);
ax2.YAxis(1).Color = natureColors(2,:);
ax2.YAxis(2).Color = natureColors(4,:);
xticks(ax2,rws.value);

sgtitle('Q2 策略对关键管理参数的敏感性','FontWeight','bold');
exportPaperFigure(fig, figureDir, 'fig_q2_parameter_sensitivity');

fprintf('Q2 图表已生成至：%s\n', figureDir);

function styleAxes(ax,dateTicks)
    grid(ax,'on'); box(ax,'on');
    ax.GridAlpha = 0.15; ax.LineWidth = 0.8;
    ax.FontName = 'Microsoft YaHei'; ax.FontSize = 10.5;
    ax.XTick = dateTicks;
    ax.XTickLabel = cellstr(string(dateTicks,'MM-dd'));
end

function styleNumericAxes(ax)
    grid(ax,'on'); box(ax,'on');
    ax.GridAlpha = 0.15; ax.LineWidth = 0.8;
    ax.FontName = 'Microsoft YaHei'; ax.FontSize = 10.5;
end

function exportPaperFigure(fig, outDir, stem)
    pdfPath = fullfile(outDir, [stem '.pdf']);
    pngPath = fullfile(outDir, [stem '.png']);
    exportgraphics(fig,pdfPath,'ContentType','vector','BackgroundColor','white');
    exportgraphics(fig,pngPath,'Resolution',600,'BackgroundColor','white');
end
