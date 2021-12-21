import numpy as np
import astropy.units as u
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from astropy.table import Table
import astropy.table as tab
from .utils import deg2rad
from . import pointing


class Telescope:

    _id = 0
    def __init__(self, x, y, z, focal, camera_radius, deg=False):

        self.x = x.to(u.m)
        self.y = y.to(u.m)
        self.z = z.to(u.m)
        self.focal = focal.to(u.m)
        self.camera_radius = camera_radius.to(u.m)
        self.alt = u.Quantity(0, u.rad)
        self.az = u.Quantity(0, u.rad)
        Telescope._id += 1
        self.id = Telescope._id
        self.table = self.make_table(deg=deg)
    
    def __repr__(self):
        return self.table.__repr__()

    def point_to_altaz(self, alt, az):
        self.alt = alt.to(u.rad)
        self.az = az.to(u.rad)
        self.update_table(["alt", "az", "pointing"])

    @property
    def zenith(self):
        return np.pi/2.*u.rad - self.alt

    @property
    def fov(self):
        """
        Area of the field of view in rad**2
        """
        return u.Quantity(np.pi * (self.camera_radius / self.focal)**2, u.rad**2)

    @property
    def position(self):
        return np.array([self.x.to(u.m).value, self.y.to(u.m).value, self.z.to(u.m).value]*u.m)

    def point_to_object(self, object):
        """
        Point to object.

        Parameters
        ----------
        object: numpy.array([x, y, z])
        """
        GT = np.sqrt(((self.position - object) ** 2).sum())
        alt_tel = np.arcsin((-self.z.value + object[2]) / GT)
        az_tel = np.arctan2((- self.y.value + object[1]), (- self.x.value + object[0]))
        self.point_to_altaz(alt_tel * u.rad, az_tel * u.rad)
        self.update_table(["alt", "az", "pointing"])

    @property
    def pointing_vector(self):
        # return pointing.alt_az_to_vector(self.alt, self.az)
        return np.array([np.cos(self.alt.to(u.rad))*np.cos(self.az.to(u.rad)),
                         -np.cos(self.alt.to(u.rad))*np.sin(self.az.to(u.rad)),
                         np.sin(self.alt.to(u.rad))])

    def make_table(self, deg=False):
        properties = [[self.id, self.x.value, self.y.value, self.z.value, self.focal, 
                       self.alt.value, self.az.value, self.zenith.value, 
                       self.fov.value, *tuple(self.pointing_vector),
                       ]]
        
        label = ["id", "x", "y", "z", "focal", "alt", "az", "zn", "fov", "p_x", "p_y", "p_z"]
        units = ["", u.m, u.m, u.m, u.m, u.rad, u.rad, u.rad, u.rad**2, "", "", ""]
        dtype = [np.int] + [np.float for i in range(len(units)-1)]
        table = Table(np.asarray(properties, dtype="object"), names=label, units=units, dtype=dtype)
        
        for col in table.columns[5:]:
            table[col].info.format = '{:.3f}'
        
        if deg:
            table =deg2rad(table, deg=deg)
            return table
        else:
            return table

    def update_table(self, vals, deg=False):
        for val in vals:
            if val == "pointing":
                new_val = self.pointing_vector
                for i, v in enumerate(["p_x", "p_y", "p_z"]):
                    self.table[v] = new_val[i]
                
            else:
                self.table[val] = getattr(self, val)
            
    def convert_unit(self, deg=True):
        self.table = deg2rad(self.table, deg)
        return self.table

class Array:

    def __init__(self, telescope_list):
        
        self.telescopes = telescope_list
        self.__create_table__()

    def __repr__(self):
        return self.table.__repr__()

    def __create_table__(self):
        table = []
        for tel in self.telescopes:
            table.append(tel.table)
        
        self.table = tab.vstack(table)

        self.table.add_column(self.distance2tel, name="d_tel")
        self.table["d_tel"].unit = u.m
        self.table["d_tel"].info.format = "{:.2f}"

    def convert_unit(self, deg=True):
        self.table = deg2rad(self.table, deg)
        return self.table
    
    @property
    def positions_array(self):
        """
        all telescopes positions as an array

        Returns
        -------
        np.array
        """
        return np.array([tel.position for tel in self.telescopes])

    @property
    def positions_table(self):
        """
        all telescopes positions as a table

        Returns
        -------
        astropy.table
        """
        return self.table["x", "y", "z"]
        
    @property
    def pointing_vectors(self):
        """
        all telescopes pointing vectors as an array

        Returns
        -------
        np.array
        """
        return np.array([tel.pointing_vector for tel in self.telescopes])
        
    @property        
    def pointing_table(self):
        """
        all telescopes pointing vectors as a table

        Returns
        -------
        astropy.table
        """
        
        return self.table["p_x", "p_y", "p_z"]
    
    @property
    def barycenter(self):
        return self.positions_array.mean(axis=0)

    @property
    def distance2tel(self):
        return np.sqrt(np.sum((self.positions_array - self.barycenter)**2, axis=1))

    def calc_mean(self, columns, table=None):

        if table == None:
            table = self.table

        if np.size(columns) == 1:
            columns = [columns]
        
        mean = []
        for column in columns:
            if column in ["p_x", "p_y", "p_z"]:
                mean.append(np.average(table[column], weights=table["d_tel"]))
            else:
                mean.append(np.mean(table[column]))
        return mean

    def divergent_pointing(self, div, alt_mean, az_mean):
        """
        Divergent pointing given a parameter div.
        Update pointing of all telescopes of the array

        Parameters
        ----------
        div: float between 0 and 1
        alt_mean: `astropy.Quantity`
            mean alt pointing
        az_mean: `astropy.Quantity`
            mean az pointing
        """
        if type(alt_mean) != u.Quantity:
            print("[Warning] The unit of the input alt is assumed to be 'deg'")
            alt_mean = alt_mean*u.deg

        if type(az_mean) != u.Quantity:
            print("[Warning] The unit of the input az is assumed to be 'deg'")
            az_mean = az_mean*u.deg

        if div > 1 or div < 0:
            print("[Error] The div value should be between 0 and 1.")
        elif div==0:
            for tel in self.telescopes:
                tel.point_to_altaz(alt_mean, az_mean)
        else:
            G = pointing.pointG_position(self.barycenter, div, alt_mean, az_mean)
            for tel in self.telescopes:
                alt_tel, az_tel = pointing.tel_div_pointing(tel.position, G)
                tel.point_to_altaz(alt_tel*u.rad, az_tel*u.rad)
        
        self.__create_table__()


    def display(self, projection=None, ax=None, group=False, **kwargs):
        """
        Display the array

        Parameters
        ----------
        projection: str
            any combination of 'x', 'y', and 'z'
        ax: `matplotlib.pyplot.axes`
        kwargs: args for `pyplot.scatter`, `pyplot.scatter`

        Returns
        -------
        ax: `matplotlib.pyplot.axes`
        """
        proj = []
        for axis in ["x", "y", "z"]:
            if axis in projection:
                proj.append(axis)

        if group:
            tel_group = self.table.group_by("focal")
            color = ["tab:blue", "tab:orange", "tab:green"]
        else:
            tel_group = self.table
            color = ["black"]

        if len(proj) == 1:
            ax = plt.gca() if ax is None else ax

            for i, [tels, color] in enumerate(zip(tel_group.groups, color)):
                for val in tels[proj[0]]:
                    ax.axvline(val, color=color, label='group_{}'.format(i), **kwargs)

            ax.set_xlabel("{} [m]".format(proj[0]))
            ax.set_yticks([0, 1])
        
        elif len(proj) == 2:
            
            ax = plt.gca() if ax is None else ax
            
            scale = 1
            
            xb = self.calc_mean(proj[0])
            yb = self.calc_mean(proj[1])
            xbv = self.calc_mean("p_"+proj[0])
            ybv = self.calc_mean("p_"+proj[1])
        
            
            for i, [tels, color] in enumerate(zip(tel_group.groups, color)):
                xx = tels[proj[0]]
                yy = tels[proj[1]]
                xv = tels["p_"+proj[0]]
                yv = tels["p_"+proj[1]]
                
                ax.scatter(xx, yy, color=color, label='group_{}'.format(i), **kwargs)
                ax.quiver(xx, yy, xv, yv, color=color)

            ax.scatter(xb, yb, marker='+', label='barycenter', color="r")
            ax.quiver(xb, yb, xbv, ybv, color="r")
            ax.set_xlabel("{} [m]".format(proj[0]))
            ax.set_ylabel("{} [m]".format(proj[1]))

            ax.grid('on')
            ax.axis('equal')
            xlim = ax.get_xlim()
            ylim = ax.get_ylim()
            ax.set_xlim(xlim[0] - 0.25 * np.abs(xlim[0]), xlim[1] + 0.25 * np.abs(xlim[1]))
            ax.set_ylim(ylim[0] - 0.25 * np.abs(ylim[0]), ylim[1] + 0.25 * np.abs(ylim[1]))
            ax.legend(frameon=False)

        else:
            ax = plt.figure(figsize=(8, 8)).add_subplot(111, projection='3d')

            scale = 1

            max_range = []
            for axis in ["x", "y", "z"]:
                max_range.append(self.table[axis].max() - self.table[axis].min())

            max_range = max(max_range)

            for i, [tels, color] in enumerate(zip(tel_group.groups, color)):
                xx = tels["x"]
                yy = tels["y"]
                zz = tels["z"]

                Xb = scale * max_range * np.mgrid[-1:2:2, -1:2:2, -1:2:2][0].flatten() + scale * (xx.max() + xx.min())
                Yb = scale * max_range * np.mgrid[-1:2:2, -1:2:2, -1:2:2][1].flatten() + scale * (yy.max() + yy.min())
                Zb = scale * max_range * np.mgrid[-0.01:2:2, -0.01:2:2, -0.01:2:2][2].flatten() + scale * (zz.max() + zz.min())
                
                for xb, yb, zb in zip(Xb, Yb, Zb):
                    ax.plot([xb], [yb], [zb], 'w')
                    ax.quiver(xx, yy, zz, 
                            tels["p_x"], tels["p_y"], tels["p_z"],
                            color=color,
                            length=max_range,
                            label='group_{}'.format(i),
                            )
             
            ax.set_xlabel('x [m]')
            ax.set_ylabel('y [m]')
            ax.set_zlabel('z [m]')
            
        return ax


    def _display_2d(self, projection='xy', ax=None, **kwargs):
        """
        Display the array

        Parameters
        ----------
        projection: str
            'xy', 'xz' or 'yz'
        ax: `matplotlib.pyplot.axes`
        kwargs: args for `pyplot.scatter`

        Returns
        -------
        ax: `matplotlib.pyplot.axes`
        """
        ax = plt.gca() if ax is None else ax
        if 'color' not in kwargs:
            kwargs['color'] = 'black'

        if projection=='xy':
            xx = self.positions_array[:, 1]
            yy = self.positions_array[:, 0]
            xb = self.barycenter[1]
            yb = self.barycenter[0]
            xv = self.pointing_vectors[:, 1]
            yv = self.pointing_vectors[:, 0]
            xlabel = 'y [m]'
            ylabel = 'x [m]'

        elif projection=='xz':
            xx = self.positions_array[:, 0]
            yy = self.positions_array[:, 2]
            xb = self.barycenter[0]
            yb = self.barycenter[2]
            xv = self.pointing_vectors[:, 0]
            yv = self.pointing_vectors[:, 2]
            xlabel = 'x [m]'
            ylabel = 'z [m]'

        elif projection=='yz':
            xx = self.positions_array[:, 1]
            yy = self.positions_array[:, 2]
            xb = self.barycenter[1]
            yb = self.barycenter[2]
            xv = self.pointing_vectors[:, 1]
            yv = self.pointing_vectors[:, 2]
            xlabel = 'y [m]'
            ylabel = 'z [m]'

        else:
            breakpoint()

        scale = np.max([xx, yy]) / 10.

        ax.scatter(xx, yy, **kwargs, label='telescopes')
        ax.scatter(xb, yb, marker='+', label='barycenter')
        ax.quiver(xx, yy, xv, yv,
                  color=kwargs['color'],
                  scale=scale,
                  )

        ax.set_ylabel(ylabel)
        ax.set_xlabel(xlabel)
        ax.grid('on')
        ax.axis('equal')
        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        ax.set_xlim(xlim[0] - 0.25 * np.abs(xlim[0]), xlim[1] + 0.25 * np.abs(xlim[1]))
        ax.set_ylim(ylim[0] - 0.25 * np.abs(ylim[0]), ylim[1] + 0.25 * np.abs(ylim[1]))
        return ax

    def _display_3d(self):
        #TODO: fix pointing quiver length issue
        fig = plt.figure()
        ax = fig.add_subplot(111, projection='3d')

        X = self.positions_array[:, 0]
        Y = self.positions_array[:, 1]
        Z = self.positions_array[:, 2]
        max_range = np.array([X.max() - X.min(), Y.max() - Y.min(), Z.max() - Z.min()]).max()
        scale = 1
        Xb = scale * max_range * np.mgrid[-1:2:2, -1:2:2, -1:2:2][0].flatten() + scale * (X.max() + X.min())
        Yb = scale * max_range * np.mgrid[-1:2:2, -1:2:2, -1:2:2][1].flatten() + scale * (Y.max() + Y.min())
        Zb = scale * max_range * np.mgrid[-0.01:2:2, -0.01:2:2, -0.01:2:2][2].flatten() + scale * (Z.max() + Z.min())
        # Comment or uncomment following both lines to test the fake bounding box:
        for xb, yb, zb in zip(Xb, Yb, Zb):
            ax.plot([xb], [yb], [zb], 'w')

        ax.quiver(X,
                  Y,
                  Z,
                  self.pointing_vectors[:, 0],
                  self.pointing_vectors[:, 1],
                  self.pointing_vectors[:, 2],
                  color='black',
                  length=max_range,
                  )

        ax.set_xlabel('x [m]')
        ax.set_ylabel('y [m]')
        ax.set_zlabel('z [m]')
        # ax.axis('equal')

        return ax



