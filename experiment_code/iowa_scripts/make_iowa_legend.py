"""
Generates two standalone legend figures for the Iowa county visualizations.

Outputs:
    figures/iowa/iowa_population_size_legend.png
        A horizontal legend showing node size scaled to three reference population
        values (10,000 / 100,000 / 1,000,000), matching the 1/500 scaling used in
        the Iowa graph visualizations.
    figures/iowa/iowa_population_composition_legend.png
        A horizontal legend showing the orange/blue color encoding for counties
        that are entirely group X or entirely group Y.
"""
import typer
import matplotlib.pyplot as plt

def main():
    plt.rcParams.update({"font.family": "serif", "mathtext.fontset": "cm", #setting to latex font
                        "font.size": 18, "savefig.dpi": 300})

    fig, ax = plt.subplots(figsize=(6, 1.5))
    ax.set_axis_off()

    ref_pops = [10000, 100000, 1000000]
    size_handles = [
        ax.scatter([], [], s=p/500, facecolor='none', edgecolor='gray',
                label=f'{p:,}')
        for p in ref_pops
    ]

    ax.legend(handles=size_handles, title='Population Size',
            edgecolor='black',
            loc='center', frameon=False,
            ncol=len(ref_pops), columnspacing=3, handletextpad=0.4)

    fig.savefig('figures/iowa/iowa_population_size_legend.png', dpi=300, bbox_inches='tight')

    fig, ax = plt.subplots(figsize=(5, 1.2))
    ax.set_axis_off()

    color_handles = [
    ax.scatter([], [], s=150, color='#FFA812', label='All group X', edgecolors= 'black'),
        ax.scatter([], [], s=150, color='#2267BC', label='All group Y', edgecolors='black'),
    ]

    ax.legend(handles=color_handles, title='Population Composition',
            loc='center', frameon=False,
            ncol=len(color_handles), columnspacing=3, handletextpad=0.4)

    fig.savefig('figures/iowa/iowa_population_composition_legend.png', dpi=300, bbox_inches='tight')

if __name__ == "__main__":
    typer.run(main)