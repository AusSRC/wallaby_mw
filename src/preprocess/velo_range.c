// Compilation: gcc -O3 -o velo_range velo_range.c -lm

// This script takes a position in J2000 equatorial coordinates
// and prints out the approximate frequency range occupied by
// Galactic HI emission in that direction.

#include <stdlib.h>
#include <stdio.h>
#include <math.h>

#define VDEV  70.0
#define RMAX  20.0
#define ZDISC  5.0
#define RSUN   8.5
#define FHI   1.42040575e+9
#define SOL   299792.458

double rotation_curve(double r);
double scale_height(double r);
int main(int argc, char* argv[]);


// -----------------------------------------------------
// Function to return rotation velocity for given radius
// -----------------------------------------------------

double rotation_curve(double r)
{
	// Note: r is expected to be in kpc, vrot in km/s
	r = fabs(r);
	if(r > RMAX) r = RMAX;

	// MW rotation curve from Clemens (1985) for R0 = 8.5 kpc, v0 = 220 km/s:
	double rotcur[4][8] = {
		{    0.0000, 3069.81000, -15809.80000, 43980.100000, -68287.3000000, 54904.0000000, -17731.00000000, 0.00000000},
		{  325.0912, -248.14670,    231.87099,  -110.735310,     25.0730060,    -2.1106250,      0.00000000, 0.00000000},
		{-2342.6564, 2507.60391,  -1024.06876,   224.562732,    -28.4080026,     2.0697271,     -0.08050808, 0.00129348},
		{  234.8800,    0.00000,      0.00000,     0.000000,      0.0000000,     0.0000000,      0.00000000, 0.00000000} };
		double breaks[4] = {0.00, 0.09, 0.45, 1.60};

	int index = 3;
	while(r < 8.5 * breaks[index]) --index;

	double vrot = 0.0;
	for(int order = 0; order < 8; ++order) vrot += rotcur[index][order] * pow(r, order);

	return vrot;
}


// --------------------------------------------------------
// Function to return scale height of disc for given radius
// --------------------------------------------------------

double scale_height(double r)
{
	// Note: r and z are expected to be in kpc.
	r = fabs(r);
	if(r < RSUN / 2.0) return ZDISC / 2.0;
	else return ZDISC * (r / RSUN);
}


// -------------
// Main function
// -------------

int main(int argc, char* argv[])
{
	if(argc != 3)
	{
		printf("Usage: ./velo_range <ra> <dec>\n");
		return 1;
	}

	// J2000 input coordinates in deg
	const double alpha = M_PI * atof(argv[1]) / 180.0;
	const double delta = M_PI * atof(argv[2]) / 180.0;

	// Constants for J2000 -> Galactic coordinate transformation
	const double a0 = 192.859496 * M_PI / 180.0;
	const double d0 =  27.128353 * M_PI / 180.0;
	const double l0 = 122.932000 * M_PI / 180.0;

	// Convert Equatorial to Galactic coordinates
	const double glon = l0 - atan2(cos(delta) * sin(alpha - a0), sin(delta) * cos(d0) - cos(delta) * sin(d0) * cos(alpha - a0));
	const double glat = asin(sin(delta) * sin(d0) + cos(delta) * cos(d0) * cos(alpha - a0));

	// Initiate velocity range with arbitrary large values:
	double v1 =  1.0e+9;
	double v2 = -1.0e+9;

	// Cast ray away from the sun to determine radial velocity range of gas:
	for(double distance = 0.0; distance < RSUN + RMAX; distance += 0.1)
	{
		double height  = distance * fabs(sin(glat));
		double targetX = distance * sin(glon) * cos(glat);
		double targetY = RSUN - distance * cos(glon) * cos(glat);
		double radius  = sqrt(targetX * targetX + targetY * targetY);

		if(height > ZDISC) break;

		double vRad = (rotation_curve(radius) * (RSUN / radius) - rotation_curve(RSUN)) * sin(glon) * cos(glat);
		if(vRad < v1) v1 = vRad;
		if(vRad > v2) v2 = vRad;
	}

	// Include deviation velocity:
	if(v1 > 0.0) v1 = 0.0;
	if(v2 < 0.0) v2 = 0.0;
	v1 -= VDEV;
	v2 += VDEV;

	// Convert to frequency
	const double f1 = FHI / (1.0 + v1 / SOL);
	const double f2 = FHI / (1.0 + v2 / SOL);

	printf("%.3f\t%.3f\n", v1, v2);
	printf("%.9e\t%.9e\n", f2, f1);

	return 0;
}
